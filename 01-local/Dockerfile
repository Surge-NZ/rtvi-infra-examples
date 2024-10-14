# Use Python base image
FROM python:3.12.4-bookworm

# Set working directory
WORKDIR /app

# Copy bot and runner files to the container
COPY bot/ /app/bot/
COPY runner/ /app/runner/

# Verify copied files
RUN ls -la /app/bot && ls -la /app/runner

# Install dependencies for both bot and runner
RUN pip install --no-cache-dir --upgrade -r /app/bot/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/runner/requirements.txt

# Make bot.py executable
RUN chmod +x /app/bot/bot.py

# Set environment variables
ENV LOG_LEVEL=INFO
ENV DAILY_API_KEY=${DAILY_API_KEY}
ENV CARTESIA_API_KEY=${CARTESIA_API_KEY}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV TTS_API_KEY=${TTS_API_KEY}
ENV AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
ENV AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
ENV AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
ENV TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
ENV TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
ENV TWILIO_PHONE_NUMBER=${TWILIO_PHONE_NUMBER}
ENV TWILIO_TWIML_URL=${TWILIO_TWIML_URL}

# Expose port for runner service
EXPOSE 7860

# Start the bot runner server
CMD ["python", "/app/runner/bot_runner.py", "--host", "0.0.0.0", "--port", "7860", "--reload"]

