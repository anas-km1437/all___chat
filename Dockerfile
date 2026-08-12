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
# تحديث أداة pip أولاً ثم تثبيت الحزم لضمان عدم وجود أخطاء في التوافق
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد الرفع وإعطائه كافة الصلاحيات لتجنب أخطاء رفع الصور والفيديو
RUN mkdir -p static/uploads && chmod -R 777 static/uploads
RUN chmod -R 777 /app

# فتح البورت الخاص بـ Render
EXPOSE $PORT

# تشغيل التطبيق عبر gunicorn مع ربطه بمتغير البيئة الديناميكي PORT
CMD gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT app:app