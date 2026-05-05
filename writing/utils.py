from .models import *
import os
import json
import mimetypes
import base64
from openai import OpenAI
from others.models import Results


def _load_image_base64(image_field):
    """
    Reads an ImageField file from disk and returns its base64 string.
    """
    try:
        image_path = image_field.path
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"Could not load graph image: {e}")
        return None


def get_result(answers, session, user):

    if isinstance(session, (str, uuid.UUID)):
        session = WritingTask.objects.get(id=session)

    # Use the session to get the linked questions
    tasks = list(session.question.all().order_by('level'))
    task_ids = [str(t.id) for t in tasks]

    if isinstance(answers, dict):
        answers_list = [answers[k] for k in sorted(answers.keys(), key=lambda x: int(x))]
    elif isinstance(answers, list):
        answers_list = answers
    else:
        answers_list = [str(answers)]

    task_sections  = []   
    image_parts    = []   
    answers_for_db = {}   

    for i, task in enumerate(tasks):
        user_answer = answers_list[i] if i < len(answers_list) else ""

        answers_for_db[str(task.id)] = {
            "task_title"   : task.title,
            "task_type"    : task.type,
            "task_level"   : task.level,
            "task_question": task.question,
            "user_answer"  : user_answer,
            "has_image"    : bool(task.type == "graph" and task.image),
        }

        if task.type == "graph" and task.image:
            img_base64 = _load_image_base64(task.image)
            if img_base64:
                image_parts.append(img_base64)
                task_sections.append(
                    f"--- TASK {i + 1} (Level {task.level} | Type: Graph/Chart) ---\n"
                    f"Task Question: {task.question}\n\n"
                    f"[Note: The graph image for Task {i + 1} has been provided above. "
                    f"Evaluate whether the student's description accurately reflects it.]\n\n"
                    f"Student Answer:\n{user_answer}\n"
                )
            else:
                task_sections.append(
                    f"--- TASK {i + 1} (Level {task.level} | Type: Graph/Chart) ---\n"
                    f"Task Question: {task.question}\n\n"
                    f"Student Answer:\n{user_answer}\n"
                )
        else:
            task_sections.append(
                f"--- TASK {i + 1} (Level {task.level} | Type: Essay) ---\n"
                f"Task Question: {task.question}\n\n"
                f"Student Answer:\n{user_answer}\n"
            )

    combined_tasks = "\n\n".join(task_sections)

    graph_note = (
        "\nIMPORTANT: For graph/chart tasks, you have been provided the actual graph image. "
        "Use it to verify whether the student accurately identified key trends, data points, "
        "and comparisons. Penalise factual inaccuracies about the graph.\n"
        if image_parts else ""
    )

    prompt_text = f"""You are an expert IELTS Writing examiner.
{graph_note}
A student has submitted the following IELTS Writing test responses:

{combined_tasks}

Evaluate the student's responses based on official IELTS Writing band descriptors and return a structured JSON feedback report.
Return ONLY valid JSON with this exact structure (no markdown, no explanation outside the JSON):

{{
  "score": <overall band score as float, e.g. 7.0>,
  "criteria": {{
    "Task Achievement"      : <band 1-9 as float>,
    "Coherence & Cohesion"  : <band 1-9 as float>,
    "Lexical Resource"      : <band 1-9 as float>,
    "Grammar & Accuracy"    : <band 1-9 as float>
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
  "answers": [
    {{
      "task"    : <task level as int, e.g. 1>,
      "type"    : "<graph or text>",
      "band"    : <individual task band score as float>,
      "feedback": "<2-3 sentence specific feedback for this task>"
    }}
  ],
  "performance_breakdown": "<2-3 sentence overall summary of the student's writing performance>"
}}
"""

    # ── 6. Call OpenRouter API ────────────────────────────────────────────────
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        content_list = [{"type": "text", "text": prompt_text}]
        for img_b64 in image_parts:
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}"
                }
            })

        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {
                    "role": "user",
                    "content": content_list
                }
            ],
            response_format={ "type": "json_object" }
        )
        raw_text = response.choices[0].message.content.strip()
        feedback = json.loads(raw_text)

    except Exception as e:
        print("Gemini API error in writing get_result:", e)
        fallback_band = 5.0
        feedback = {
            "score"   : fallback_band,
            "criteria": {
                "Task Achievement"    : fallback_band,
                "Coherence & Cohesion": fallback_band,
                "Lexical Resource"    : fallback_band,
                "Grammar & Accuracy"  : fallback_band,
            },
            "strengths": [
                "Attempted all tasks",
                "Maintained a recognisable structure",
            ],
            "areas_for_improvement": [
                "Develop task-specific vocabulary",
                "Improve coherence between paragraphs",
                "Review grammar and sentence variety",
            ],
            "answers": [
                {
                    "task"    : task.level,
                    "type"    : task.type,
                    "band"    : fallback_band,
                    "feedback": "AI evaluation is currently unavailable. Please try again later.",
                }
                for task in tasks
            ],
            "performance_breakdown": (
                "AI evaluation could not be completed at this time. "
                "Your responses have been saved successfully."
            ),
        }

    feedback["db_responses"] = answers_for_db


    
    score_val = feedback.get('score', '0.0')

    tasks_data = []
    for t in tasks:
        tasks_data.append({
            "id": t.id,
            "title": t.title,
            "type": t.type,
            "question": t.question,
            "level": t.level,
            "image": t.image.url if t.image else None
        })

    count = Results.objects.filter(user=user, type="writing").count() + 1

    result = Results.objects.create(
        user      = user,
        name      = f"Results of Writing Test {count}",
        score     = str(score_val),
        answers   = answers_for_db,
        feedback  = feedback,
        type      = "writing",
        questions = tasks_data
    )

    return feedback, result.id
