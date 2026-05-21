import random
from .models import *
from django.db.models import Count
import os
import json
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


def _normalize_user_answer(raw_user_answer):
    if raw_user_answer is None:
        return None, "[NO ANSWER PROVIDED]"
    if isinstance(raw_user_answer, str):
        cleaned = raw_user_answer.strip()
        return (None, "[NO ANSWER PROVIDED]") if not cleaned else (cleaned, cleaned)
    if isinstance(raw_user_answer, list):
        normalized = []
        for item in raw_user_answer:
            item_value, _ = _normalize_user_answer(item)
            if item_value is not None:
                normalized.append(item_value)
        if not normalized:
            return None, "[NO ANSWER PROVIDED]"
        return normalized, str(normalized)
    if isinstance(raw_user_answer, dict):
        normalized = {}
        for key, value in raw_user_answer.items():
            item_value, _ = _normalize_user_answer(value)
            if item_value is not None:
                normalized[key] = item_value
        if not normalized:
            return None, "[NO ANSWER PROVIDED]"
        return normalized, json.dumps(normalized, ensure_ascii=False)
    cleaned = str(raw_user_answer).strip()
    return (None, "[NO ANSWER PROVIDED]") if not cleaned else (raw_user_answer, cleaned)

from others.models import Results




def create_question_set():
    """
    Creates a new QuestionSet session with randomly selected passages for each IELTS level.
    Returns the QuestionSet instance.
    """
    # Fetch random IDs for each level
    passage_data = ReadingPassage.objects.filter(level__in=[1, 2, 3]).values_list('id', 'level')
    
    grouped_ids = {1: [], 2: [], 3: []}
    for pid, level in passage_data:
        if level in grouped_ids:
            grouped_ids[level].append(pid)
            
    ids = []
    for level in [1, 2, 3]:
        if grouped_ids[level]:
            ids.append(random.choice(grouped_ids[level]))
    
    queryset = ReadingPassage.objects.filter(id__in=ids).prefetch_related('questions')

    # Create a fresh session for this exam
    question_set = QuestionSet.objects.create()
    question_set.passages.set(queryset)
    
    # Pre-calculate and store answers for evaluation
    answers_map = {}
    for passage in queryset:
        for question in passage.questions.all():
            answers_map[str(question.question_number)] = question.answer
    
    question_set.answers = answers_map
    question_set.save()
    
    return question_set



def get_result(set_id, answers):

    try:
        question_set = QuestionSet.objects.get(id=set_id)
    except QuestionSet.DoesNotExist:
        return {"error": "Question set not found", "score": 0.0}

    correct_answers = question_set.answers or {}

    # ── 2. Normalise user answers to a dict {str(q_num): answer} ─────────────
    # Already normalised by the view — answers is a plain dict {"1": val, "2": val, ...}

    # ── 3. Score calculation ──────────────────────────────────────────────────
    correct_count  = 0
    total_questions = len(correct_answers)
    per_question_detail = []

    for q_num, correct_answer in correct_answers.items():
        raw_user_answer = answers.get(str(q_num))
        is_correct  = False
        user_answer, display_answer = _normalize_user_answer(raw_user_answer)

        if isinstance(correct_answer, list):
            if isinstance(user_answer, list):
                is_correct = any(
                    str(ua).strip().lower() == str(ca).strip().lower()
                    for ua in user_answer for ca in correct_answer
                )
            else:
                is_correct = (
                    user_answer is not None and
                    str(user_answer).strip().lower() in [str(ca).strip().lower() for ca in correct_answer]
                )
        elif isinstance(correct_answer, dict):
            # Matching type: {left_key: right_value}
            if isinstance(user_answer, dict):
                is_correct = all(
                    str(user_answer.get(k, '')).strip().lower() == str(v).strip().lower()
                    for k, v in correct_answer.items()
                )
        else:
            is_correct = (
                user_answer is not None and
                str(user_answer).strip().lower() == str(correct_answer).strip().lower()
            )

        if is_correct:
            correct_count += 1

        per_question_detail.append({
            'question_number': q_num,
            'correct_answer' : correct_answer,
            'user_answer'    : display_answer,
            'is_correct'     : is_correct,
        })

    # IELTS Reading band score conversion (40-question scale approximation)
    raw_score = correct_count
    accuracy_pct = (correct_count / total_questions * 100) if total_questions else 0

    def raw_to_band(raw, total):
        if total == 0:
            return 0.0
        pct = raw / total
        if pct >= 0.97: return 9.0
        if pct >= 0.93: return 8.5
        if pct >= 0.87: return 8.0
        if pct >= 0.80: return 7.5
        if pct >= 0.73: return 7.0
        if pct >= 0.67: return 6.5
        if pct >= 0.60: return 6.0
        if pct >= 0.53: return 5.5
        if pct >= 0.47: return 5.0
        if pct >= 0.40: return 4.5
        if pct >= 0.33: return 4.0
        return 3.5

    overall_band = raw_to_band(raw_score, total_questions)

    # ── 4. Build prompt — blank answers already normalized to "[NO ANSWER PROVIDED]"
    unanswered = sum(1 for item in per_question_detail if item['user_answer'] == "[NO ANSWER PROVIDED]")
    summary_lines = []
    for item in per_question_detail:
        status_str = "✓ Correct" if item['is_correct'] else "✗ Wrong"
        summary_lines.append(
            f"  Q{item['question_number']}: {status_str} "
            f"(correct: {item['correct_answer']}, given: {item['user_answer']})"
        )
    performance_summary = "\n".join(summary_lines)

    prompt = f"""
You are an expert IELTS Reading examiner. A student has just completed an IELTS Reading test.

Test Statistics:
- Total Questions  : {total_questions}
- Correct Answers  : {correct_count}
- Unanswered       : {unanswered}
- Accuracy         : {accuracy_pct:.1f}%
- Estimated Band   : {overall_band}

Per-question breakdown (answers labeled "[NO ANSWER PROVIDED]" mean the student left that question completely blank):
{performance_summary}

RULES — follow these strictly:
1. Any question showing "[NO ANSWER PROVIDED]" means the student gave NO answer. Report it as unanswered. Do NOT invent or guess what the student might have written.
2. Only base your feedback on what is literally shown above. Do not assume, hallucinate, or fill in missing answers.
3. Scores must reflect the actual results above — do not inflate or deflate.
4. Be very strict about accuracy. If many questions are wrong or unanswered, reflect this in the performance_breakdown as poor performance.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{{
  "score": <overall_band_score as float, e.g. 7.5>,
  "criteria": {{
    "Reading Accuracy"    : <band 1-9 as float>,
    "Skimming & Scanning": <band 1-9 as float>,
    "Vocabulary Range"   : <band 1-9 as float>,
    "Time Management"    : <band 1-9 as float>
  }},
  "strengths": [
    "<strength 1>",
    "<strength 2>",
    "<strength 3>"
  ],
  "areas_for_improvement": [
    "<area 1>",
    "<area 2>",
    "<area 3>"
  ],
  "performance_breakdown": "<2-3 sentence honest summary. Mention unanswered questions explicitly if any>"
}}
"""

    # ── 5. Call OpenRouter API ────────────────────────────────────────────────
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        raw_text = response.choices[0].message.content.strip()
        feedback = _clean_and_parse_json(response.choices[0].message.content)

    except Exception as e:
        print("Gemini API error in reading get_result:", e)
        # Graceful fallback – return rule-based result so the endpoint doesn't break
        feedback = {
            "score"   : overall_band,
            "criteria": {
                "Reading Accuracy"    : overall_band,
                "Skimming & Scanning" : round(overall_band - 0.5, 1),
                "Vocabulary Range"    : round(overall_band - 0.5, 1),
                "Time Management"     : round(overall_band, 1),
            },
            "strengths": [
                "Completed the test",
                f"Answered {correct_count} out of {total_questions} questions correctly",
            ],
            "areas_for_improvement": [
                "Review incorrect answers carefully",
                "Practice skimming for main ideas",
                "Build academic vocabulary",
            ],
            "performance_breakdown": (
                f"You scored {correct_count}/{total_questions} ({accuracy_pct:.1f}%), "
                f"which corresponds to an IELTS band of approximately {overall_band}. "
                "Keep practising to improve your reading speed and accuracy."
            ),
        }

    # Always attach raw score for the view to save
    feedback["score"]      = feedback.get("score", overall_band)
    feedback["raw_score"]  = raw_score
    feedback["total"]      = total_questions
    feedback["accuracy"]   = round(accuracy_pct, 1)

    return feedback



def save_result(set_id, answers, user):
    try:
        question_set = QuestionSet.objects.get(id=set_id)
    except QuestionSet.DoesNotExist:
        return None, "Question set not found"
    try:
        
        title = Results.objects.filter(user=user, type='reading').count() + 1
        result = Results.objects.create(
            name = f"Results of Reading Test {title}",
            user=user,
            answers=answers,
            type = 'reading',
            score = 0
        )

        passages_list = []
        for passage in question_set.passages.prefetch_related('questions'):
            p_data = {
                'id': passage.id,
                'title': passage.title,
                'content': passage.content,
                'level': passage.level,
                'questions': list(passage.questions.values('id', 'question_number', 'question', 'question_type', 'options', 'answer'))
            }
            passages_list.append(p_data)
        
        result.questions = passages_list
        result.save()

        correct_count = 0
        total_questions = 0

        for question_number, correct_answer in question_set.answers.items():
            total_questions += 1
            user_answer = answers.get(question_number)

            if isinstance(correct_answer, list):
                if isinstance(user_answer, list):
                    if any(ans.lower() == correct.lower() for ans in user_answer for correct in correct_answer):
                        correct_count += 1
                else:
                    if user_answer and user_answer.lower() in [ans.lower() for ans in correct_answer]:
                        correct_count += 1
            else:
                if user_answer and str(user_answer).lower() == str(correct_answer).lower():
                    correct_count += 1

        result.score = correct_count
        result.save()

        return True, result

    except Exception as e:
        print("Error in reading save result: ", e)
        return False, str(e)

    
