#!/bin/bash
set -e

# Create superuser/admin user automatically if it doesn't exist
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()

email = 'admin@gmail.com'
password = '123'

# Check if user already exists
if not User.objects.filter(email=email).exists():
    user = User.objects.create_superuser(
        email=email,
        password=password,
        name='Admin User'
    )
    user.role = 'ADMIN'
    user.is_staff = True
    user.is_superuser = True
    user.save()
    print(f'✓ Admin user created: {email}')
else:
    user = User.objects.get(email=email)
    user.is_staff = True
    user.is_superuser = True
    user.role = 'ADMIN'
    user.save()
    print(f'✓ Admin user already exists: {email}')
EOF
