import os
import json
import base64
from openai import OpenAI
import re

def _clean_and_parse_json(raw: str) -> dict:
    """Robustly parse AI JSON responses that may include markdown fences or trailing commas."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith('```'):
        lines = text.split('\n')
        # Remove first line (```json or ```) and last line (```)
        lines = lines[1:] if lines[0].startswith('```') else lines
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    # Remove trailing commas before } or ] (common AI mistake)
    text = re.sub(r',\s*(\}|\])', r'\1', text)
    return json.loads(text)


OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'gpt-4o-mini')

def get_client():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

def get_openrouter_response(prompt: str, model: str = None) -> str:
    """Helper to call OpenRouter API using OpenAI client"""
    client = get_client()
    response = client.chat.completions.create(
        model=model or OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content



def generate_speaking_questions() -> dict:

    prompt = """
    You are an official IELTS Speaking examiner creating a brand-new, unique test session.
    Generate a complete IELTS Speaking test with all 3 parts. Be creative and vary topics each time.

    Rules:
    - Part 1: YOU MUST NOT pick a single topic for Part 1. You MUST generate exactly 5 natural, conversational questions. EACH of the 5 questions MUST be about a COMPLETELY DIFFERENT and UNRELATED everyday topic. For example: Q1 about your hometown, Q2 about your favorite food, Q3 about your morning routine, Q4 about a recent holiday, and Q5 about learning languages. If any two questions are about the same topic, you have failed. Set the topic field to exactly "Random Assorted Topics".
    - Part 2: A cue card on a specific topic. It must have:
        * A clear topic title
        * A 1-sentence cue card description ("Describe a time when..." or "Describe a place/person/thing...")
        * Exactly 4 bullet points the candidate should cover (You should say...)
    - Part 3: 5 follow-up DISCUSSION questions related to the Part 2 topic — deeper, more abstract,
      opinion-based questions an examiner would ask after the cue card.

    Respond ONLY with a valid JSON object. No markdown, no extra text:
    {
      "part1": {
        "topic": "Random Assorted Topics",
        "questions": [
          "<q1 about topic A>",
          "<q2 about topic B (completely unrelated to A)>",
          "<q3 about topic C (completely unrelated to A and B)>",
          "<q4 about topic D (completely unrelated to others)>",
          "<q5 about topic E (completely unrelated to others)>"
        ]
      },
      "part2": {
        "topic": "<short topic label>",
        "cue_card": "<the cue card instruction sentence>",
        "points_to_cover": ["<point1>", "<point2>", "<point3>", "<point4>"]
      },
      "part3": {
        "topic": "<short topic label>",
        "questions": ["<q1>", "<q2>", "<q3>", "<q4>", "<q5>"]
      }
    }
    """

    raw = get_openrouter_response(prompt)
    return _clean_and_parse_json(raw)



def get_transcript(file) -> str:
    """
    Converts audio file to base64 and gets transcript via OpenRouter.
    """
    if not file:
        return "[NO ANSWER PROVIDED]"
        
    name = getattr(file, 'name', 'audio.mp3')
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else 'mp3'
    
    # Read file and encode to base64
    file.seek(0)
    audio_data = file.read()
    base64_audio = base64.b64encode(audio_data).decode('utf-8')
    
    mime_type = f"audio/{ext}"
    if ext == 'mp3': mime_type = "audio/mpeg"

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": (
                                "Please transcribe the spoken words in this audio file accurately and completely. "
                                "Output ONLY the verbatim transcript — no timestamps, no speaker labels, no comments. "
                                "Preserve punctuation naturally as spoken."
                            )
                        },
                        {
                            "type": "image_url", # OpenRouter uses image_url for multimodal content
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_audio}"
                            }
                        }
                    ]
                }
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Transcription error: {e}")
        return "Could not generate transcript."

def get_result_multimodal(audio1, audio2, audio3, questions: dict) -> dict:
    """
    Highly optimized: Transcribes and evaluates all 3 speaking parts in ONE AI call.
    Reduces latency by ~70% compared to sequential transcribe-then-evaluate calls.
    """
    p1 = questions.get('part1', {})
    p2 = questions.get('part2', {})
    p3 = questions.get('part3', {})

    p1_qs = '\n'.join(f'- {q}' for q in p1.get('questions', []))
    p2_cue = p2.get('cue_card', '')
    p2_pts = '\n'.join(f'- {pt}' for pt in p2.get('points_to_cover', []))
    p3_qs = '\n'.join(f'- {q}' for q in p3.get('questions', []))

    # Helper to prepare multimodal audio parts
    def prepare_audio_part(file, label):
        if not file:
            return {"type": "text", "text": f"--- {label}: [NO AUDIO PROVIDED] ---"}
        
        file.seek(0)
        audio_data = file.read()
        base64_audio = base64.b64encode(audio_data).decode('utf-8')
        name = getattr(file, 'name', 'audio.mp3')
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else 'mp3'
        mime_type = f"audio/{ext}"
        if ext == 'mp3': mime_type = "audio/mpeg"
        
        return {
            "type": "image_url", # OpenRouter uses image_url for multimodal content
            "image_url": { "url": f"data:{mime_type};base64,{base64_audio}" }
        }

    messages_content = [
        {
            "type": "text",
            "text": f"""
You are an official IELTS Speaking examiner. Your task is to:
1. Transcribe the spoken words in the provided audio files.
2. Evaluate the candidate's performance across all 3 parts based on official IELTS band descriptors.

EXAM DETAILS:
=== PART 1 — Interview ===
Questions: {p1_qs}

=== PART 2 — Cue Card ===
Task: {p2_cue}
Points: {p2_pts}

=== PART 3 — Two-way Discussion ===
Questions: {p3_qs}

RULES:
- If any audio part is missing, transcribe it as "[NO ANSWER PROVIDED]" and score that specific part as 0.
- If a response is completely off-topic, contains random noise/text, or is in a language other than English, you MUST score that part between 1 and 3 depending on the severity.
- Provide verbatim transcripts for each part.
- Evaluate Fluency, Pronunciation, Grammar, and Vocabulary strictly based on IELTS descriptors.

Return ONLY a JSON object:
{{
  "transcripts": {{
    "part1": "...",
    "part2": "...",
    "part3": "..."
  }},
  "overall_band_score": <float 0-9>,
  "fluency": <float 0-9>,
  "pronunciation": <float 0-9>,
  "grammar": <float 0-9>,
  "vocabulary": <float 0-9>,
  "feedback": "...",
  "part_feedback": {{ "part1": "...", "part2": "...", "part3": "..." }},
  "suggestions": ["...", "...", "..."]
}}
"""
        }
    ]

    # Append audio parts
    messages_content.append(prepare_audio_part(audio1, "PART 1 AUDIO"))
    messages_content.append(prepare_audio_part(audio2, "PART 2 AUDIO"))
    messages_content.append(prepare_audio_part(audio3, "PART 3 AUDIO"))

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": messages_content}],
            response_format={ "type": "json_object" }
        )
        raw = response.choices[0].message.content.strip()
        return _clean_and_parse_json(raw)
    except Exception as e:
        print(f"Multimodal evaluation error: {e}")
        return {"error": "Failed to evaluate speaking.", "score": 0}


def get_result(part1_transcript: str, part2_transcript: str, part3_transcript: str,
               questions: dict) -> dict:
    """
    Standard evaluation using text transcripts.
    """
    p1 = questions.get('part1', {})
    p2 = questions.get('part2', {})
    p3 = questions.get('part3', {})

    p1_qs = '\n'.join(f'- {q}' for q in p1.get('questions', []))
    p2_cue = p2.get('cue_card', '')
    p2_pts = '\n'.join(f'- {pt}' for pt in p2.get('points_to_cover', []))
    p3_qs = '\n'.join(f'- {q}' for q in p3.get('questions', []))

    p1_text = str(part1_transcript or "[NO ANSWER PROVIDED]")
    p2_text = str(part2_transcript or "[NO ANSWER PROVIDED]")
    p3_text = str(part3_transcript or "[NO ANSWER PROVIDED]")

    prompt = f"""
You are an official IELTS Speaking examiner. Evaluate the candidate's responses.
PART 1: {p1_qs} | Answer: {p1_text}
PART 2: {p2_cue} | Answer: {p2_text}
PART 3: {p3_qs} | Answer: {p3_text}

Evaluate using official descriptors and return ONLY a JSON object:
{{
  "overall_band_score": <float>,
  "fluency": <float>,
  "pronunciation": <float>,
  "grammar": <float>,
  "vocabulary": <float>,
  "feedback": "...",
  "part_feedback": {{ "part1": "...", "part2": "...", "part3": "..." }},
  "suggestions": ["...", "...", "..."]
}}
"""
    raw = get_openrouter_response(prompt).strip()
    return _clean_and_parse_json(raw)