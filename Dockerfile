# استخدام نسخة بايثون خفيفة ومتوافقة
FROM python:3.10-slim

# تحديد مسار العمل داخل السيرفر
WORKDIR /app

# نسخ ملف الاعتماديات وتثبيت الحزم
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد الرفع وإعطائه كافة الصلاحيات لتجنب أخطاء رفع الصور والفيديو
RUN mkdir -p static/uploads && chmod -R 777 static/uploads
RUN chmod -R 777 /app

# فتح البورت الخاص بـ Hugging Face
EXPOSE 7860

# تشغيل التطبيق عبر gunicorn مع ربطه بالبورت 7860
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "-b", "0.0.0.0:7860", "app:app"]