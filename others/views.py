import os
import json
from .models import *
from openai import OpenAI
from .serializers import *
from .models import *
from datetime import timedelta
from django.shortcuts import render
from django.db.models import Max, FloatField
from django.db.models.functions import Cast
from rest_framework import generics, status, permissions, views
from rest_framework.response import Response
from django.utils import timezone
from django.http import HttpResponse
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from listening.models import Question as ListeningQuestion, ListeningTask
from reading.models import ReadingQuestion, QuestionSet
from writing.models import WritingQuestion
from django.contrib.auth import get_user_model
User = get_user_model()
from reading.utils import create_question_set as reading_question_set
from speaking.utils import generate_speaking_questions as speaking_question_set

from listening.serializers import ListeningTaskSerializer
from writing.serializers import WritingQuestionSerializer
from reading.serializers import QuestionSetSerializer as ReadingQuestionSetSerializer
from .serializers import MockTaskSerializer

# Evaluation functions
from listening.utils import get_result as listening_eval
from reading.utils import get_result as reading_eval
from writing.utils import get_result as writing_eval
from speaking.utils import get_result as speaking_eval, get_transcript
from concurrent.futures import ThreadPoolExecutor

# Create your views here.



class BlogListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = BlogSerializer
    queryset = Blog.objects.all().order_by('-created_at')



class BlogDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = BlogSerializer
    queryset = Blog.objects.all()
    lookup_field = 'id'



class DashBoardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        results = Results.objects.filter(user=user).order_by('-created_at')
        
        # Get latest results for each module
        reading = results.filter(type='reading').first()
        writing = results.filter(type='writing').first()
        listening = results.filter(type='listening').first()
        speaking = results.filter(type='speaking').first()

        def get_band(res):
            if not res: return 0.0
            try:
                val = float(res.score)
                # If score is > 9, it's likely a raw score (e.g. 28/40), convert to band
                if val > 9:
                    if val >= 39: return 9.0
                    if val >= 37: return 8.5
                    if val >= 35: return 8.0
                    if val >= 33: return 7.5
                    if val >= 30: return 7.0
                    if val >= 27: return 6.5
                    if val >= 23: return 6.0
                    if val >= 19: return 5.5
                    if val >= 15: return 5.0
                    return 4.5
                return val
            except:
                return 0.0

        scores = [get_band(reading), get_band(writing), get_band(listening), get_band(speaking)]
        valid_scores = [s for s in scores if s > 0]
        avg_band = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 0.0

        # Current Month Data
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_results = results.filter(created_at__gte=start_of_month)

        # Chart 1: Weekly Overall Band (Current Month)
        weekly_chart = []
        for i in range(4):
            w_start = start_of_month + timedelta(days=i*7)
            w_end = w_start + timedelta(days=7)
            if i == 3: # Include rest of the month in the last week
                if now.month == 12:
                    next_month = now.replace(year=now.year+1, month=1, day=1)
                else:
                    next_month = now.replace(month=now.month+1, day=1)
                w_end = next_month
            
            w_results = monthly_results.filter(created_at__range=[w_start, w_end])
            w_bands = [get_band(r) for r in w_results]
            w_avg = round(sum(w_bands) / len(w_bands), 1) if w_bands else 0.0
            weekly_chart.append({
                "week": f"Week {i+1}",
                "avg_band": w_avg
            })

        # Chart 2: Monthly Module Averages
        module_chart = []
        for m_type in ['reading', 'writing', 'listening', 'speaking']:
            m_results = monthly_results.filter(type=m_type)
            m_bands = [get_band(r) for r in m_results]
            m_avg = round(sum(m_bands) / len(m_bands), 1) if m_bands else 0.0
            module_chart.append({
                "module": m_type.capitalize(),
                "avg_band": m_avg
            })

        data = {
            "user": {
                "name": user.name or user.email,
                "image": request.build_absolute_uri(user.image.url) if user.image else None,
                "overall_band": avg_band,
            },
            "charts": {
                "weekly_overall": weekly_chart,
                "module_averages": module_chart
            },
            "recent_activities": [
                {
                    "name" : res.name,
                    "score" : res.score,
                    "created_at" : res.created_at,
                    
                } for res in results[:5]
            ]
        }
        
        return Response(data)
    



class MessagesView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        name = data.get('name')
        email = data.get('email')
        message = data.get('message')

        if not name or not email or not message:
            return Response(
                {'status': False, 'error': 'Missing fields'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        Messages.objects.create(
            name=name,
            email=email,
            message=message,
        )
        
        return Response({
            "status": True,
            "log": "Message sent successfully"
        })





class ContactView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        data = ContactInfo.objects.all().first()
        return Response({
            "status": True,
            "data": {
                "email": data.email or "",
                "phone": data.phone or "",
                "address": data.address or "",
                "support_timing": data.support_timing or "",
            }
        })



class FAQView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        data = FAQ.objects.all()
        return Response({
            "status": True,
            "log": [
                {
                    "title": faq.title,
                    "description": faq.description,
                } for faq in data
            ]
        })



class LeaderboardView(views.APIView):

    def get(self, request):
        data = Results.objects.all()
        # Cast score to FloatField for accurate numeric Max and sorting
        top6 = (data.values('user').annotate(
            max_score=Max(Cast('score', output_field=FloatField()))
        ).order_by('-max_score')[:6])
        
        results = []
        review = [
                    "I've been practicing IELTS on this platform for a few weeks now, and I can really see improvement in my skills. The exercises are clear and helpful, and I like how I can track my progress.",
                    "This website has made my IELTS preparation much easier. The practice tests feel realistic, and the feedback helps me understand where I need to improve.",
                    "I enjoy using this platform for my IELTS practice. The lessons are well-structured, and it keeps me motivated to study regularly.",
                    "Preparing for IELTS here has been a great experience. The interface is simple, and I can practice anytime without feeling overwhelmed.",
                    "This platform is very useful for IELTS students like me. I especially like the variety of questions and how it helps build my confidence.",
                    "I've tried other resources, but this website stands out. It’s easy to use, and I feel more prepared for my IELTS exam every day."
                    ]

        for index, i in enumerate(top6):
            user = User.objects.get(id=i['user'])
            # Order by created_at to correctly identify first and last attempts
            user_results = data.filter(user=user).order_by('created_at')
            cur = user_results.last()
            old = user_results.first()
            results.append({
                "name": user.name or user.email,
                "image": request.build_absolute_uri(user.image.url) if user.image else None,
                "score_before": float(old.score) if old else 0.0,
                "score_after": float(cur.score) if cur else 0.0,
                "time": cur.created_at if cur else None,
                "review": review[index % len(review)]
            })
        
        return Response({
            "status": True,
            "log": results
        })


class DetailedFeedbackView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, result_id):
        try:
            result = Results.objects.get(id=result_id, user=request.user)
            return Response({
                "status": True,
                "data": result.feedback,
                "name": result.name,
                "type": result.type,
                "created_at": result.created_at
            })
        except Results.DoesNotExist:
            return Response({
                "status": False,
                "error": "Result not found"
            }, status=status.HTTP_404_NOT_FOUND)



class DownloadReportView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, result_id):
        try:
            result = Results.objects.get(id=result_id, user=request.user)
            feedback = result.feedback or {}

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=2*cm, leftMargin=2*cm,
                topMargin=2*cm, bottomMargin=2*cm
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
            heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#4361ee'), spaceBefore=14, spaceAfter=6)
            subheading_style = ParagraphStyle('Subheading', parent=styles['Heading3'], fontSize=11, textColor=colors.HexColor('#2d3436'), spaceBefore=8, spaceAfter=4)
            body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=16, textColor=colors.HexColor('#333333'))
            label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#888888'))

            story = []

            # Header
            story.append(Paragraph('IELTS Performance Report', title_style))
            story.append(Paragraph(f'Test: {result.name}', label_style))
            story.append(Paragraph(f'Date: {result.created_at.strftime("%B %d, %Y")}  |  Overall Band: {result.score}', label_style))
            story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#4361ee'), spaceAfter=12))

            if result.type == 'mock':
                # --- MOCK TEST REPORT ---
                story.append(Paragraph('Mock Exam Module Summary', heading_style))
                table_data = [['Module', 'Score']]
                for mod in ['listening', 'reading', 'writing', 'speaking']:
                    m_data = feedback.get(mod, {})
                    table_data.append([mod.capitalize(), str(m_data.get('score', '0.0'))])
                
                table_data.append(['OVERALL BAND', str(result.score)])
                
                t = Table(table_data, colWidths=[10*cm, 6*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4361ee')),
                    ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                    ('ALIGN', (1,0), (1,-1), 'CENTER'),
                    ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#f0f4ff')),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
                    ('PADDING', (0,0), (-1,-1), 8),
                ]))
                story.append(t)
                story.append(Spacer(1, 15))

                # Module Details
                story.append(Paragraph('Module Performance Analysis', heading_style))
                for mod in ['listening', 'reading', 'writing', 'speaking']:
                    m_data = feedback.get(mod, {})
                    summary = m_data.get('performance_breakdown') or m_data.get('feedback')
                    if summary:
                        story.append(Paragraph(mod.capitalize(), subheading_style))
                        story.append(Paragraph(str(summary), body_style))
                        story.append(Spacer(1, 5))

            else:
                # --- STANDARD SINGLE MODULE REPORT ---
                summary = feedback.get('performance_breakdown', '')
                if summary:
                    story.append(Paragraph('Overall Summary', heading_style))
                    story.append(Paragraph(summary, body_style))
                    story.append(Spacer(1, 8))

                criteria = feedback.get('criteria', {})
                if criteria:
                    story.append(Paragraph('Score Breakdown', heading_style))
                    table_data = [['Criteria', 'Score']]
                    for key, val in criteria.items():
                        table_data.append([key, str(val)])
                    t = Table(table_data, colWidths=[12*cm, 4*cm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4361ee')),
                        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f4ff'), colors.white]),
                        ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
                        ('PADDING',    (0,0), (-1,-1), 6),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 12))

                strengths = feedback.get('strengths', [])
                if strengths:
                    story.append(Paragraph('Strengths', heading_style))
                    for s in strengths:
                        story.append(Paragraph(f'• {s}', body_style))
                    story.append(Spacer(1, 8))

                improvements = feedback.get('areas_for_improvement', [])
                if improvements:
                    story.append(Paragraph('Areas for Improvement', heading_style))
                    for imp in improvements:
                        story.append(Paragraph(f'• {imp}', body_style))

            doc.build(story)
            buffer.seek(0)

            filename = f"ielts_report_{result.type}_{result.id}.pdf"
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Results.DoesNotExist:
            return Response({"error": "Result not found"}, status=404)


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


class AIFeedbackView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, result_id):
        try:
            result = Results.objects.get(id=result_id, user=request.user)
            
            # Use cached detailed analysis if available
            if result.feedback and "detailed_analysis" in result.feedback:
                return Response({
                    "status": True,
                    "data": result.feedback["detailed_analysis"]
                })

            if result.type == 'mock':
                # --- MOCK TEST ANALYSIS ---
                test_data = {
                    "overall_score": result.score,
                    "module_scores": {
                        "listening": result.feedback.get('listening', {}).get('score'),
                        "reading": result.feedback.get('reading', {}).get('score'),
                        "writing": result.feedback.get('writing', {}).get('score'),
                        "speaking": result.feedback.get('speaking', {}).get('score'),
                    },
                    "module_feedbacks": {
                        "listening": result.feedback.get('listening', {}).get('performance_breakdown'),
                        "reading": result.feedback.get('reading', {}).get('performance_breakdown'),
                        "writing": result.feedback.get('writing', {}).get('performance_breakdown'),
                        "speaking": result.feedback.get('speaking', {}).get('performance_breakdown'),
                    },
                    # We pass a summary of answers to keep it fast
                    "writing_tasks": result.answers.get('writing', {}),
                    "speaking_transcripts": result.answers.get('speaking', {})
                }

                prompt = f"""
                You are a Senior IELTS Examiner. Analyze this FULL MOCK EXAM result.
                Overall Band: {result.score}
                
                Data: {json.dumps(test_data, indent=2)}

                Provide a comprehensive, high-speed analysis in JSON format:
                {{
                    "overall_summary": "Overall evaluation of the student's readiness for the real exam.",
                    "module_analysis": {{
                        "listening": "Quick take on listening accuracy and focus.",
                        "reading": "Quick take on reading comprehension and speed.",
                        "writing": "Analysis of writing tasks, grammar, and coherence.",
                        "speaking": "Analysis of fluency, pronunciation, and vocabulary."
                    }},
                    "analysis": [
                        {{
                            "question": "Critical weakness identified",
                            "status": "incorrect",
                            "student_answer": "...",
                            "correct_answer": "...",
                            "explanation": "Explain a major pattern of error found across the test.",
                            "examiner_tip": "Advice to fix this pattern."
                        }}
                    ],
                    "action_plan": ["Step 1", "Step 2", "Step 3"]
                }}
                """
            else:
                # --- STANDARD SINGLE MODULE ANALYSIS ---
                raw_answers = result.answers or {}
                sanitized_answers = {}
                for k, v in raw_answers.items():
                    if v is None or (isinstance(v, str) and not v.strip()):
                        sanitized_answers[k] = "[NO ANSWER PROVIDED]"
                    elif isinstance(v, dict):
                        sanitized_v = dict(v)
                        inner = v.get('user_answer', '')
                        if inner is None or (isinstance(inner, str) and not inner.strip()):
                            sanitized_v['user_answer'] = "[NO ANSWER PROVIDED]"
                        sanitized_answers[k] = sanitized_v
                    else:
                        sanitized_answers[k] = v

                test_data = {
                    "type": result.type,
                    "score": result.score,
                    "questions": result.questions,
                    "user_answers": sanitized_answers,
                }

                prompt = f"""
                You are an expert IELTS examiner. Analyze the following student test result and provide a deep-dive performance analysis.
                Test Type: {result.type}
                Overall Score/Band: {result.score}

                For each question (especially incorrect ones):
                1. Identify the question number/identifier.
                2. Evaluate the student's answer.
                3. If wrong, explain precisely what led to the mistake.
                4. Provide the correct answer and rationale.
                5. Give a targeted "Examiner Tip".

                Student Data:
                {json.dumps(test_data, indent=2)}

                Return response as JSON:
                {{
                    "overall_summary": "...",
                    "analysis": [
                        {{
                            "question": "...",
                            "status": "correct/incorrect",
                            "student_answer": "...",
                            "correct_answer": "...",
                            "explanation": "...",
                            "examiner_tip": "..."
                        }}
                    ],
                    "action_plan": ["..."]
                }}
                """

            # Call AI
            api_key = os.getenv("OPENROUTER_API_KEY")
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            
            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            
            raw_content = response.choices[0].message.content
            try:
                detailed_analysis = _clean_and_parse_json(raw_content)
                # Store it in the feedback field for future use
                if not result.feedback:
                    result.feedback = {}
                result.feedback["detailed_analysis"] = detailed_analysis
                result.save()
                
                return Response({
                    "status": True,
                    "data": detailed_analysis
                })
            except Exception as e:
                print(f"Error parsing AI feedback: {e}")
                return Response({
                    "status": False,
                    "error": "Failed to parse AI response. Please try again."
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Results.DoesNotExist:
            return Response({"error": "Result not found"}, status=404)
        except Exception as e:
            print(f"Error in AIFeedbackView: {e}")
            return Response({
                "status": False,
                "error": "Failed to generate detailed feedback. Please try again later."
            }, status=500)




class HomeData(views.APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request):
        try:
            l_count = ListeningQuestion.objects.count()
            r_count = ReadingQuestion.objects.count()
            w_count = WritingQuestion.objects.count()
            total_question_sets = QuestionSet.objects.count()

            total_questions_count = l_count + r_count + w_count + total_question_sets
            
            data = {
                "total_questions": f"{total_questions_count}+",
                "listening_questions": l_count,
                "reading_questions": r_count,
                "writing_questions": w_count,
                "speaking_questions": "Unlimited (AI Generated)",
                "total_users": User.objects.count(),
                "total_tests_taken": total_question_sets
            }
            
            return Response({
                "status": True,
                "data": data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())

            return Response({
                "status": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class MockTaskSubmitView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        mock_task_id = request.data.get('task_id')
        if not mock_task_id:
            return Response({"status": False, "error": "task_id is required"}, status=400)

        try:
            mock_task = MockTask.objects.get(id=mock_task_id, user=request.user)
        except MockTask.DoesNotExist:
            return Response({"status": False, "error": "Mock task not found"}, status=404)

        if mock_task.completed:
            return Response({"status": False, "error": "Mock task already submitted"}, status=400)

        # Retrieve answers from request
        l_answers = request.data.get('listening_answers', {})
        r_answers = request.data.get('reading_answers', {})
        w_answers = request.data.get('writing_answers', {})
        # Speaking Audio Files
        part1_audio = request.FILES.get('speaking_part1')
        part2_audio = request.FILES.get('speaking_part2')
        part3_audio = request.FILES.get('speaking_part3')

        try:
            # 1. Listening Evaluation
            l_set_id = mock_task.l_set.get('id') if mock_task.l_set else None
            l_feedback = listening_eval(l_set_id, l_answers) if l_set_id else {"score": 0, "error": "No listening task"}
            l_score = float(l_feedback.get('score', 0))

            # 2. Reading Evaluation
            r_set_id = mock_task.r_set.get('id') if mock_task.r_set else None
            r_feedback = reading_eval(r_set_id, r_answers) if r_set_id else {"score": 0, "error": "No reading task"}
            r_score = float(r_feedback.get('score', 0))

            # 3. Writing Evaluation
            w_ids = [q.get('id') for q in mock_task.w_set] if mock_task.w_set else []
            w_instances = WritingQuestion.objects.filter(id__in=w_ids)
            # writing_eval returns (feedback, result_id)
            w_feedback, _ = writing_eval(w_answers, w_instances, request.user) if w_instances.exists() else ({"score": 0}, None)
            w_score = float(w_feedback.get('score', 0))

            # 4. Speaking Evaluation (Transcribe first, then eval)
            s_set = mock_task.s_set or {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                f1 = executor.submit(get_transcript, part1_audio) if part1_audio else None
                f2 = executor.submit(get_transcript, part2_audio) if part2_audio else None
                f3 = executor.submit(get_transcript, part3_audio) if part3_audio else None
                
                t1 = f1.result() if f1 else "[NO ANSWER PROVIDED]"
                t2 = f2.result() if f2 else "[NO ANSWER PROVIDED]"
                t3 = f3.result() if f3 else "[NO ANSWER PROVIDED]"

            s_feedback = speaking_eval(t1, t2, t3, s_set) if s_set else {"score": 0}
            s_score = float(s_feedback.get('score', 0))

            # Calculate Overall Band Score (standard IELTS rounding: nearest 0.5)
            # Average the 4 scores, multiply by 2, round to nearest integer, divide by 2
            overall_band = round((l_score + r_score + w_score + s_score) / 4 * 2) / 2

            # Create the Unified Mock Result
            mock_result = Results.objects.create(
                user=request.user,
                name=f"Full Mock Test Results - {timezone.now().strftime('%Y-%m-%d')}",
                score=str(overall_band),
                type='mock',
                questions={
                    "listening": mock_task.l_set,
                    "reading": mock_task.r_set,
                    "writing": mock_task.w_set,
                    "speaking": mock_task.s_set
                },
                answers={
                    "listening": l_answers,
                    "reading": r_answers,
                    "writing": w_answers,
                    "speaking": s_answers
                },
                feedback={
                    "overall_score": overall_band,
                    "listening": l_feedback,
                    "reading": r_feedback,
                    "writing": w_feedback,
                    "speaking": s_feedback
                }
            )

            mock_task.completed = True
            mock_task.save()

            return Response({
                "status": True,
                "message": "Full mock test submitted successfully",
                "result_id": str(mock_result.id),
                "overall_score": overall_band,
                "feedback": mock_result.feedback
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({
                "status": False,
                "error": f"Evaluation failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class GetMockTask(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        user = request.user
        # Plan check
        # if user.subscriptions.filter(plan__name="free").exists():
        #     return Response({
        #         "status": False,
        #         "error": "Upgrade your plan to access this feature"
        #     }, status=status.HTTP_403_FORBIDDEN)
            
        try:
            mock_task = MockTask.objects.filter(user=request.user, completed=False).first()

            if not mock_task:
                # 1. Listening
                l_instance = ListeningTask.objects.order_by('?').first()
                l_data = ListeningTaskSerializer(l_instance,context={'request': request}).data if l_instance else None
                
                # 2. Reading
                r_instance = reading_question_set()
                r_data = ReadingQuestionSetSerializer(r_instance,context={'request': request}).data if r_instance else None
                
                # 3. Writing
                queryset = WritingQuestion.objects.all()
                task1 = queryset.filter(level=1).order_by('?').first()
                task2 = queryset.filter(level=2).order_by('?').first()
                w_questions = [q for q in [task1, task2] if q is not None]
                w_data = WritingQuestionSerializer(w_questions, many=True,context={'request': request}).data
                
                # 4. Speaking
                s_data = speaking_question_set()

                mock_task = MockTask.objects.create(
                    user=request.user,
                    l_set=l_data,
                    r_set=r_data,
                    w_set=w_data,
                    s_set=s_data,
                )

            if not mock_task:
                return Response({
                    "status": False,
                    "error": "Failed to create mock task"
                }, status=status.HTTP_404_NOT_FOUND)
            
            data = MockTaskSerializer(mock_task, context={'request': request}).data
            rem_time = mock_task.remaining_time()
            data['remaining_time'] = int(rem_time.total_seconds()) if rem_time.total_seconds() > 0 else 0

            return Response({
                "status": True,
                "message": "Mock task fetched successfully",
                "data": data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({
                "status": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)