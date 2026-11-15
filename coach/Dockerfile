# The hosted coach (coach/server.py). Build from the repository root:
#   docker build -f coach/Dockerfile -t omniriff-coach .
#   docker run -p 8787:8787 -e ANTHROPIC_API_KEY=... -e ELEVENLABS_API_KEY=... \
#     -e OMNIRIFF_COACH_PASSCODE=... -v omniriff-coach:/data omniriff-coach
FROM python:3.12-slim

WORKDIR /app
COPY coach/requirements.txt coach/requirements.txt
RUN pip install --no-cache-dir -r coach/requirements.txt "numpy>=1.26" "scipy>=1.11"

# Only what the coach imports: no engine audio I/O, no dashboard, no keys.
COPY protocol/ protocol/
COPY coach/ coach/
COPY tools/ears/ tools/ears/
COPY audio/__init__.py audio/fileio.py audio/takes.py audio/engine.py audio/dsp.py audio/looper.py audio/reverb.py audio/
COPY vision/__init__.py vision/eyes.py vision/hand_window.py vision/hand_log.py vision/technique.py vision/

ENV HOST=0.0.0.0 PORT=8787 OMNIRIFF_COACH_DATA=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8787
CMD ["python", "-m", "coach.server"]
