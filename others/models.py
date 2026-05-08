from django.db import models
from django.contrib.auth import get_user_model
import uuid
from datetime import timedelta
from django.utils import timezone
User = get_user_model()
from ckeditor.fields import RichTextField
# Create your models here.

class Blog(models.Model):
    title = models.CharField(max_length=200)
    content = RichTextField()
    image = models.ImageField(upload_to='blog_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title



class Task(models.Model):
    MODULE_TYPES = (
        ('reading', 'Reading'),
        ('writing', 'Writing'),
        ('listening', 'Listening'),
        ('speaking', 'Speaking'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    question = models.UUIDField(max_length=100)
    module = models.CharField(max_length=100, choices=MODULE_TYPES)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.email + " " + self.module

    def remaining_time(self):
        return self.created_at + timedelta(minutes=60) - timezone.now()

    class Meta:
        # Prevent duplicate active tasks for the same user+module+question
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'module', 'question'],
                condition=models.Q(completed=False),
                name='unique_active_task_per_user_module_question'
            )
        ]



class Results(models.Model):
    RESULT_TYPES = (
        ('reading', 'Reading'),
        ('writing', 'Writing'),
        ('listening', 'Listening'),
        ('speaking', 'Speaking'),
        ('mock', 'Mock')
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='results')
    name = models.CharField(max_length=100)
    score = models.CharField(max_length=10, default="0.0")
    type = models.CharField(max_length=100, choices=RESULT_TYPES)
    questions = models.JSONField(blank=True, null=True)
    answers = models.JSONField(blank=True, null=True)
    feedback = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def get_count(self, module=None):
        return Results.objects.filter(user=self.user, type=module).count()



class Messages(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email + " " + self.message[:50]



class ContactInfo(models.Model):
    email = models.EmailField(default="ieltsrevice@example.com")
    phone = models.CharField(max_length=100, default="+91 1234567890")
    address = models.TextField(default="123,abc street")
    support_timing = models.TextField(default="Mon-Fri 9am-5pm")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email



class FAQ(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    




class MockTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_tasks')
    l_set = models.JSONField(blank=True, null=True)
    r_set = models.JSONField(blank=True, null=True)
    w_set = models.JSONField(blank=True, null=True)
    s_set = models.JSONField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.email
    
    def remaining_time(self):
        return self.created_at + timedelta(minutes=180) - timezone.now()
    
        