from .serializers import *
from .models import *
from .utils import *
from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from others.models import Results, Task
from subscriptions.models import Plan




class WritingTaskCreateView(generics.ListCreateAPIView):
    queryset = WritingQuestion.objects.all()
    serializer_class = WritingQuestionSerializer

    def create(self, request, *args, **kwargs):
        # Check if the data is a list (direct list or nested under 'tasks' key)
        is_many = isinstance(request.data, list)
        data = request.data
        
        if not is_many and 'tasks' in request.data and isinstance(request.data['tasks'], list):
            is_many = True
            data = request.data['tasks']
        
        if is_many:
            serializer = self.get_serializer(data=data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        
        return super().create(request, *args, **kwargs)




class GetWritingTaskView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = request.user.results.filter(type='writing').count()
        plan = request.user.subscriptions.filter(active=True).first()
        
        # If no active plan or free plan, apply limits
        if not plan or plan.plan.name == "free":
            # Get the free plan definition from the DB to get its test_limit
            free_plan = plan.plan if plan else Plan.objects.filter(name="free").first()
            limit = free_plan.test_limit if free_plan else 2 # default to 2 if something is missing
            
            if count >= limit:
                return Response({
                    "status": False,
                    "message": f"You have completed {limit} free writing tasks. Please upgrade your plan to continue."
                }, status=status.HTTP_400_BAD_REQUEST)
        try:
            task = Task.objects.get(user=request.user, module='writing', completed=False)
            session = WritingTask.objects.get(id=task.question)
            serializer = WritingTaskSerializer(session, context={'request': request, 'task': task})
            return Response({
                "status": True,
                "message": "Writing task session retrieved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Task.DoesNotExist:
            queryset = WritingQuestion.objects.all()
            task1 = queryset.filter(level=1).order_by('?').first()
            task2 = queryset.filter(level=2).order_by('?').first()
            
            questions = [q for q in [task1, task2] if q is not None]
            
            # Create a session (WritingTask)
            session = WritingTask.objects.create()
            session.question.set(questions)

            task = Task.objects.create(user=request.user, module='writing', question=session.id, completed=False)

            serializer = WritingTaskSerializer(session, context={'request': request, 'task': task})
            
            return Response({
                "status": True,
                "message": "Writing task session created successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)




class WritingResultCreateView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        answers    = request.data.get('answers', [])
        session_id = request.data.get('task_id')

        if not answers or not session_id:
            return Response(
                {"status": False, "message": "Answers and task_id (session ID) are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        Task.objects.filter(user=request.user, question=session_id, module="writing").update(completed=True)

        try:
            session = WritingTask.objects.get(id=session_id)

        except WritingTask.DoesNotExist:
            return Response(
                {"status": False, "message": "Writing session not found"},
                status=status.HTTP_404_NOT_FOUND
            )
                
        feedback, result_id = get_result(answers, session, request.user)

        if not feedback:
            return Response(
                {"status": False, "message": "Failed to evaluate writing result"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


        return Response({
            "status" : True,
            "message": "Result saved successfully",
            "id": result_id,
            "result" : feedback
        }, status=status.HTTP_201_CREATED)