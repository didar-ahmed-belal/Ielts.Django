from rest_framework import generics, views, status
from rest_framework.response import Response
from concurrent.futures import ThreadPoolExecutor, as_completed
from .models import *
from .utils import generate_speaking_questions, get_transcript, get_result
from django.db import transaction
from others.models import Results, Task
from subscriptions.models import Plan
from rest_framework.permissions import IsAuthenticated
from datetime import timedelta


class GenerateSpeakingSessionView(views.APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        count = request.user.results.filter(type='speaking').count()
        plan = request.user.subscriptions.filter(active=True).first()
        
        # If no active plan or free plan, apply limits
        if not plan or plan.plan.name == "free":
            # Get the free plan definition from the DB to get its test_limit
            free_plan = plan.plan if plan else Plan.objects.filter(name="free").first()
            limit = free_plan.test_limit if free_plan else 2 # default to 2 if something is missing
            
            if count >= limit:
                return Response({
                    "status": False,
                    "message": f"You have completed {limit} free speaking tasks. Please upgrade your plan to continue."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Clean up any duplicate incomplete tasks (safety net)
        tasks = Task.objects.filter(user=request.user, module='speaking', completed=False)
        task_count = tasks.count()
        if task_count > 1:
            latest = tasks.order_by('-created_at').first()
            tasks.exclude(id=latest.id).delete()
            task = latest
        elif task_count == 1:
            task = tasks.first()
        else:
            task = None

        if task:
            try:
                session = QuestionSet.objects.get(id=task.question)
                time = (session.start + session.duration) - timezone.now()
                total_seconds = int(time.total_seconds())
                if total_seconds <= 0:
                    duration_str = "00:00:00"
                else:
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                return Response({
                    'status': True,
                    'session_id': str(session.id),
                    **session.questions,
                    'duration': duration_str,
                })
            except QuestionSet.DoesNotExist:
                # Underlying session deleted — fall through to create a new one
                task.delete()

        # No valid active task — create a brand-new speaking session
        try:
            questions = generate_speaking_questions()
            session = QuestionSet.objects.create(questions=questions)
            Task.objects.create(user=request.user, module='speaking', question=session.id, completed=False)
            return Response({
                'status': True,
                'session_id': str(session.id),
                **questions,
                'duration': "00:14:00",
            })
        except Exception as e:
            return Response(
                {'status': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )





class SpeakingResultView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data

        part1_audio = data.get('audio1')
        part2_audio = data.get('audio2')
        part3_audio = data.get('audio3')
        session_id  = data.get('session')

        # Only session_id is required; audio parts are optional
        if not session_id:
            return Response(
                {'status': False, 'error': 'Missing field: session_id'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Load questions from DB using session_id
        try:
            question_set = QuestionSet.objects.get(id=session_id)
            questions = question_set.questions
            # Only save answers for parts where audio was actually provided
            answers_to_create = []
            if part1_audio:
                answers_to_create.append(SpeakingAnswer(session=question_set, part=1, audio=part1_audio))
            if part2_audio:
                answers_to_create.append(SpeakingAnswer(session=question_set, part=2, audio=part2_audio))
            if part3_audio:
                answers_to_create.append(SpeakingAnswer(session=question_set, part=3, audio=part3_audio))
            if answers_to_create:
                with transaction.atomic():
                    SpeakingAnswer.objects.bulk_create(answers_to_create)

        except QuestionSet.DoesNotExist:
            return Response(
                {'status': False, 'error': 'Invalid or expired session_id'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use filter+first instead of get to prevent MultipleObjectsReturned
        task = Task.objects.filter(
            user=request.user, module='speaking', question=session_id
        ).order_by('-created_at').first()

        if not task:
            return Response(
                {'status': False, 'error': 'Speaking task session not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Clean up any duplicate tasks for the same question
        Task.objects.filter(
            user=request.user, module='speaking', question=session_id
        ).exclude(id=task.id).delete()

        task.completed = True
        task.save()

        # Transcribe only audio parts that were provided; use placeholder for missing ones
        NO_ANSWER = "[NO ANSWER PROVIDED]"
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            if part1_audio:
                futures[executor.submit(get_transcript, part1_audio)] = 'part1'
            if part2_audio:
                futures[executor.submit(get_transcript, part2_audio)] = 'part2'
            if part3_audio:
                futures[executor.submit(get_transcript, part3_audio)] = 'part3'

            transcripts = {
                'part1': NO_ANSWER,
                'part2': NO_ANSWER,
                'part3': NO_ANSWER,
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    transcripts[key] = future.result()
                except Exception as e:
                    return Response(
                        {'status': False, 'error': f'Transcription failed for {key}: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        # Evaluate with Gemini
        try:
            feedback = get_result(
                part1_transcript=transcripts['part1'],
                part2_transcript=transcripts['part2'],
                part3_transcript=transcripts['part3'],
                questions=questions,
            )
        except Exception as e:
            return Response(
                {'status': False, 'error': f'Evaluation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Save result to the unified Results table
        count = Results.objects.filter(user=request.user, type='speaking').count() + 1
        result = Results.objects.create(
            user      = request.user,
            name      = f"Results of Speaking Test {count}",
            score     = str(feedback.get('overall_band_score', '0.0')),
            type      = 'speaking',
            questions = questions,
            answers   = transcripts,
            feedback  = feedback,
        )

        return Response({
            'status': True,
            'message': 'Speaking evaluated successfully',
            'transcripts': transcripts,
            'id': result.id,
            'result': feedback,
        }, status=status.HTTP_201_CREATED)

