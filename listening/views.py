import random
from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import ListeningTask, Question
from .serializers import ListeningTaskSerializer, QuestionSerializer
from others.models import Task
from subscriptions.models import Plan



class ListeningTaskListView(generics.ListCreateAPIView):
    queryset = ListeningTask.objects.all()
    serializer_class = ListeningTaskSerializer

    def create(self, request, *args, **kwargs):
        # Check if the data is a list for bulk creation
        is_many = isinstance(request.data, list)
        
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)



class ListeningTaskDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = request.user.results.filter(type='listening').count()
        plan = request.user.subscriptions.filter(active=True).first()
        
        if not plan or plan.plan.name == "free":
            # Get the free plan definition from the DB to get its test_limit
            free_plan = plan.plan if plan else Plan.objects.filter(name="free").first()
            limit = free_plan.test_limit if free_plan else 2 # default to 2 if something is missing
            
            if count >= limit:
                return Response({
                    "status": False,
                    "message": f"You have completed {limit} free listening tasks. Please upgrade your plan to continue."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Clean up any duplicate incomplete tasks (shouldn't exist, but safety net)
        tasks = Task.objects.filter(user=request.user, module='listening', completed=False)
        task_count = tasks.count()
        if task_count > 1:
            # Keep the most recent, delete the rest
            latest = tasks.order_by('-created_at').first()
            tasks.exclude(id=latest.id).delete()
            task = latest
        elif task_count == 1:
            task = tasks.first()
        else:
            task = None

        if task:
            try:
                listening_task = ListeningTask.objects.get(id=task.question)
                serializer = ListeningTaskSerializer(listening_task, context={'task': task, "request": request})
                return Response({
                    'success': True,
                    'message': 'Listening test session retrieved successfully',
                    'data': serializer.data
                })
            except ListeningTask.DoesNotExist:
                # If the underlying listening task was deleted, remove the stale task session
                task.delete()

        # If no active session exists (or one was just deleted), start a new one
        listening_task = ListeningTask.objects.order_by('?').first()
        if not listening_task:
            return Response({
                'success': False,
                'message': 'No listening tasks available',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
            
        task = Task.objects.create(user=request.user, module='listening', question=listening_task.id, completed=False)
        serializer = ListeningTaskSerializer(listening_task, context={'task': task, "request": request})
        return Response({
            'success': True,
            'message': 'Listening test session created successfully',
            'data': serializer.data
        })
from .utils import save_result, get_result

class ListeningQuestionAnswerSubmitView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
            
        task_id = data.get('task_id')
        answers = data.get('answers', [])

        if not task_id or not answers:
            return Response({
                'success': False,
                'message': 'Task ID and answers are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Use filter+first instead of get to prevent MultipleObjectsReturned
        task_session = Task.objects.filter(
            user=request.user, module='listening', question=task_id
        ).order_by('-created_at').first()

        if not task_session:
            return Response({
                'success': False,
                'message': 'Test session not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Clean up any other duplicate tasks for same question
        Task.objects.filter(
            user=request.user, module='listening', question=task_id
        ).exclude(id=task_session.id).delete()

        task_session.completed = True
        task_session.save()

        if isinstance(answers, list):
            merged = {}
            for item in answers:
                if isinstance(item, dict):
                    merged.update(item)
            answers = merged

        success, result_obj = save_result(task_id, answers, request.user)
        if not success:
            return Response({
                'success': False,
                'message': result_obj or 'Failed to save listening answers'
            }, status=status.HTTP_400_BAD_REQUEST)

        feedback_data = get_result(task_id, answers)
        result_obj.score = str(feedback_data.get('score', result_obj.score))
        result_obj.feedback = feedback_data
        result_obj.save()

        feedback_data["id"] = result_obj.id

        return Response({
            'success': True,
            'message': 'Listening answers submitted successfully',
            'data': feedback_data,
            'id': result_obj.id
        })
