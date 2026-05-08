from rest_framework import serializers
from .models import *

class BlogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Blog
        fields = '__all__'


class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Results
        fields = '__all__'


class MockTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTask
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        
        if request:
            # Fix Listening Audio URL
            if representation.get('l_set') and 'audio' in representation['l_set']:
                audio_path = representation['l_set']['audio']
                if audio_path and not audio_path.startswith('http'):
                    representation['l_set']['audio'] = request.build_absolute_uri(audio_path)
            
            # Fix Writing Image URLs
            if representation.get('w_set') and isinstance(representation['w_set'], list):
                for item in representation['w_set']:
                    if 'image' in item and item['image']:
                        image_path = item['image']
                        if image_path and not image_path.startswith('http'):
                            item['image'] = request.build_absolute_uri(image_path)
                            
        return representation