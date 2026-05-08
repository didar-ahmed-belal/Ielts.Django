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
from listening.models import Question as ListeningQuestion
from reading.models import ReadingQuestion, QuestionSet
from writing.models import WritingQuestion
from django.contrib.auth import get_user_model
User = get_user_model()


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
            body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=16, textColor=colors.HexColor('#333333'))
            label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#888888'))

            story = []

            # Header
            story.append(Paragraph('IELTS Performance Report', title_style))
            story.append(Paragraph(f'Test: {result.name}', label_style))
            story.append(Paragraph(f'Module: {result.type.capitalize()}  |  Score: {result.score}  |  Date: {result.created_at.strftime("%B %d, %Y")}', label_style))
            story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#4361ee'), spaceAfter=12))

            # Summary
            summary = feedback.get('performance_breakdown', '')
            if summary:
                story.append(Paragraph('Overall Summary', heading_style))
                story.append(Paragraph(summary, body_style))
                story.append(Spacer(1, 8))

            # Criteria scores
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
                    ('FONTSIZE',   (0,0), (-1,0), 10),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f4ff'), colors.white]),
                    ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
                    ('PADDING',    (0,0), (-1,-1), 6),
                ]))
                story.append(t)
                story.append(Spacer(1, 12))

            # Strengths
            strengths = feedback.get('strengths', [])
            if strengths:
                story.append(Paragraph('Strengths', heading_style))
                for s in strengths:
                    story.append(Paragraph(f'• {s}', body_style))
                story.append(Spacer(1, 8))

            # Areas for improvement
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

            # Prepare data for AI — sanitize answers at code level first
            raw_answers = result.answers or {}
            sanitized_answers = {}
            for k, v in raw_answers.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    sanitized_answers[k] = "[NO ANSWER PROVIDED]"
                elif isinstance(v, dict):
                    # For writing tasks: check the user_answer field inside
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
            3. If wrong, explain precisely what led to the mistake (e.g., misinterpretation of a keyword, missing a detail in the passage, grammatical error).
            4. Provide the correct answer and the rationale behind it.
            5. Give a targeted "Examiner Tip" on how to avoid this specific error in the future.

            RULES — follow these strictly:
            1. Any answer labeled "[NO ANSWER PROVIDED]" means the student gave absolutely no response. You MUST mark it as "incorrect", set student_answer to "No answer provided", and state clearly in the explanation that the student did not answer. Do NOT invent, guess, or fabricate any answer.
            2. Only base your analysis on what is literally in the data below. Do not hallucinate.
            3. Be 100% honest — act as a strict, fair teacher, not a generous one.

            Student Data:
            {json.dumps(test_data, indent=2)}

            Return the response as a structured JSON object with this exact structure:
            {{
                "overall_summary": "A 2-3 sentence summary of overall performance from an examiner's perspective.",
                "analysis": [
                    {{
                        "question": "Question text or number",
                        "status": "correct/incorrect",
                        "student_answer": "...",
                        "correct_answer": "...",
                        "explanation": "Detailed explanation of the mistake or why it was correct.",
                        "examiner_tip": "Specific advice to improve."
                    }}
                ],
                "action_plan": [
                    "3-5 concrete steps the student should take to reach a higher band score."
                ]
            }}
            """

            # Call AI
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                return Response({
                    "status": False,
                    "error": "AI configuration missing"
                }, status=500)

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            
            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            
            raw_content = response.choices[0].message.content
            try:
                detailed_analysis = _clean_and_parse_json(raw_content)
            except Exception as parse_err:
                print(f"JSON parse error in AIFeedbackView: {parse_err}")
                print(f"Raw AI response: {raw_content[:500]}")
                return Response({
                    "status": False,
                    "error": "The AI returned an invalid response. Please try again."
                }, status=500)
            
            # Store it in the feedback field for future use
            if not result.feedback:
                result.feedback = {}
            result.feedback["detailed_analysis"] = detailed_analysis
            result.save()

            return Response({
                "status": True,
                "data": detailed_analysis
            })

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
            return Response({
                "status": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            
    
            
    