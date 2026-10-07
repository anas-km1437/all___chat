# استخدام نسخة بايثون خفيفة ومتوافقة
FROM python:3.10-slim

# إعداد متغيرات البيئة لتحسين أداء بايثون على خوادم Render
# (يمنع كتابة ملفات البايت كود ويجعل السجلات تظهر فوراً في لوحة تحكم Render)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تحديد منفذ افتراضي لـ Render (عادة 10000)
ENV PORT=10000

# تحديد مسار العمل داخل السيرفر
WORKDIR /app

# نسخ ملف الاعتماديات وتثبيت الحزم
COPY requirements.txt .

# تحديث أداة pip أولاً ثم تثبيت الحزم الأساسية وحقن الحزم المفقودة يدوياً لضمان حل أخطاء التوافق والـ CORS
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir flask-cors gunicorn[eventlet]

# تثبيت أداة FFmpeg المخصصة لتشغيل ميزة سحب الكاميرا السحابية
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد الرفع وإعطائه كافة الصلاحيات لتجنب أخطاء رفع الصور والفيديو
RUN mkdir -p static/uploads && chmod -R 777 static/uploads
RUN chmod -R 777 /app

# فتح البورت الخاص بـ Render
EXPOSE $PORT

# تشغيل التطبيق عبر gunicorn مع استخدام التنسيق الدقيق الصارم لعمال الـ eventlet والـ WebSockets على بورت Render الديناميكي
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:10000", "app:app"]
