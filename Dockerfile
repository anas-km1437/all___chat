# استخدام نسخة بايثون خفيفة ومتوافقة
FROM python:3.10-slim

# إعداد متغيرات البيئة لمنع ملفات البايت كود وجعل السجلات فورية
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# تحديد مسار العمل
WORKDIR /app

# نسخ الاعتماديات
COPY requirements.txt .

# تثبيت كافة محركات التشغيل والاتصال بقاعدة البيانات لضمان عدم وجود أخطاء نقص حزم
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir flask-cors gevent gunicorn[gevent] psycopg2-binary

# تثبيت أداة FFmpeg المخصصة لتشغيل ميزة سحب الكاميرا السحابية
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد الرفع وإعطائه كافة الصلاحيات
RUN mkdir -p static/uploads && chmod -R 777 static/uploads
RUN chmod -R 777 /app

# فتح البورت الخاص بـ Render
EXPOSE $PORT

# تشغيل السيرفر باستخدام محرك gevent المستقر والآمن 100% على منصة Render
CMD gunicorn -k gevent -w 1 -b 0.0.0.0:10000 app:app
