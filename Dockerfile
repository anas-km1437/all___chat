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

# 🔥 [الحل النهائي لقفل الخطأ]: إجبار نظام الحاوية على تحديث pip وتثبيت عمال الـ eventlet بشكل مستقل تماماً رغماً عن أي قيود
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask-cors
RUN pip install --no-cache-dir eventlet
RUN pip install --no-cache-dir gunicorn
RUN pip install --no-cache-dir "gunicorn[eventlet]"

# تثبيت أداة FFmpeg المخصصة لتشغيل ميزة سحب الكاميرا السحابية
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد الرفع وإعطائه كافة الصلاحيات
RUN mkdir -p static/uploads && chmod -R 777 static/uploads
RUN chmod -R 777 /app

# فتح البورت الخاص بـ Render
EXPOSE $PORT

# 🔥 [تنسيق التشغيل الصارم]: تشغيل السيرفر بصيغة الـ Shell الصافية والمباشرة المعتمدة لحل تعارض التنفيذ
CMD gunicorn -k eventlet -w 1 -b 0.0.0.0:10000 app:app
