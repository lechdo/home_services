FROM python:3.12-alpine

# ffmpeg : requis par yt-dlp pour l'extraction audio (FFmpegExtractAudio),
# l'écriture des tags ID3 (FFmpegMetadata) et l'embarquement de la pochette
# (EmbedThumbnail).
RUN apk add --no-cache ffmpeg

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
