from .models import *
from .helper import *
from .serializers import *
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import generics, status,permissions
from rest_framework_simplejwt.tokens import RefreshToken
from subscriptions.serializers import *
from payments.serializers import PaymentSerializer
from payments.models import Payments
from rest_framework import generics, status, permissions
from rest_framework.response import Response

# Create your views here.

class SignUpView(generics.CreateAPIView):
    serializer_class = SignUpSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "status": True,
            "log": UserProfileSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)

    
class SignInView(generics.CreateAPIView):
    serializer_class = SignInSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            "status": True,
            "log": UserProfileSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_200_OK)


class UserRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return User.objects.filter(email=self.request.user.email).first()


class GetOtpView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        task = request.data.get('task', '')
        if not email:
            return Response(
                {"status": False,"log": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        res = send_otp(email, task)

        if res['status']:
            return Response({"status": True, "log": res['log']}, status=status.HTTP_200_OK)
        else:
            return Response({"status": False,"log": res['log']}, status=status.HTTP_400_BAD_REQUEST)


class OtpVerifyView(APIView):
    def post(self, request):
        email = request.data.get('email')
        otp_code = request.data.get('otp_code')

        if not email or not otp_code:
            return Response(
                {"status": False,"log": "Email and OTP code are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = verify_otp(email, otp_code)

        if result['status']:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({"status": False,"log": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                "log": UserProfileSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }, status=status.HTTP_200_OK)
        else:
            # 403 for lock, 400 for invalid/expired
            status_code = status.HTTP_403_FORBIDDEN if "Too many attempts" in result['log'] else status.HTTP_400_BAD_REQUEST
            return Response({"status": False, "log": result['log']}, status=status_code)


class ResetPassword(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        email = request.data.get('email')
        new_password = request.data.get('new_password')



        if not email or not new_password :
            return Response(
                {"error": "Email and new password are required."},
                status=400
            )
        
        elif request.user.email != email :
            return Response(
                {"error": "You can only reset your own password."},
                status=403)
        
        try:
            user = User.objects.get(email=email)
            user.set_password(new_password)
            if user.is_forgot:
                user.is_forgot = False
            user.save()
            return Response({"status": True, "log": "Password reset successfully"}, status=200)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


class GetProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = UserProfileSerializer(request.user,context={"request": request}).data
        subscription = request.user.subscriptions.filter(active=True).first()
        plan = PlanSerializers(subscription.plan).data if subscription else None
        history = Payments.objects.filter(user=request.user).order_by('-created_at')
        history = PaymentSerializer(history, many=True).data
        return Response({"status": True, "log": user, "plan": plan, "history": history}, status=200)


class ForgotPasswordCreateView(generics.CreateAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.filter(email=email).first()
        if user:
            # Generate OTP and send email
            res = send_otp(email, task='forgot_password')
            if res['status']:
                return Response({"status": True, "log": "OTP sent to your email."}, status=status.HTTP_200_OK)
            else:
                return Response({"status": False, "log": res['log']}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"status": False, "log": "User not found."}, status=status.HTTP_404_NOT_FOUND)


class ForgotPasswordVerifyView(generics.CreateAPIView):
    serializer_class = ForgotPasswordVerifySerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']
        result = verify_otp(email, otp_code)

        if not result['status']:
            return Response({"status": False, "log": result['log']}, status=status.HTTP_400_BAD_REQUEST)

        if result['status']:
            try:
                user = User.objects.get(email=email)
                user.set_password(new_password)
                token = RefreshToken.for_user(user)

                user.is_forgot = True

                user.save()
                return Response({"status": True, "log": "Password reset successfully.", "access": str(token.access_token), "refresh": str(token.refresh_token) }, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({"status": False, "log": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"status": False, "log": result['log']}, status=status.HTTP_400_BAD_REQUEST)