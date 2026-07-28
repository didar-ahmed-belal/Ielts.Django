from .models import User
from rest_framework import serializers


class SignUpSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'name', 'password', 'confirm_password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password fields do not match.")
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            name=validated_data.get('name', ''),
            password=validated_data['password']
        )
        return user


class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = User.objects.filter(email=email).first()
            if user:
                if not user.check_password(password):
                     raise serializers.ValidationError("Invalid credentials")
                if not user.is_active:
                    raise serializers.ValidationError("User is not active")
                if user.block:
                    raise serializers.ValidationError("User is blocked")
                attrs['user'] = user
                return attrs
            else:
                raise serializers.ValidationError("User not found")
        raise serializers.ValidationError("Email and password are required")


class UserProfileSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = User
        exclude = ['block', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'date_joined']
        read_only_fields = ['id', 'email', 'role']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def update(self, instance, validated_data):
        # Update name and image if provided
        instance.name = validated_data.get('name', instance.name)
        instance.image = validated_data.get('image', instance.image)

        # Handle password update
        old_password = validated_data.get('old_password')
        new_password = validated_data.get('password')

        if new_password:
            if not old_password:
                raise serializers.ValidationError({"old_password": "Current password is required to set a new password."})
            
            if not instance.check_password(old_password):
                raise serializers.ValidationError({"old_password": "Old password does not match."})
            
            instance.set_password(new_password)

        instance.save()
        return instance


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField()

