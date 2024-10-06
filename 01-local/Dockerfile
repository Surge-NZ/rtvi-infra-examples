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
ENV DAILY_API_KEY="da9d3f554c229d6aeae120569448521c9cb5af2c696e31c83f6e4ddfff41f097"
ENV CARTESIA_API_KEY="c6e8b60d-7d5a-40e1-8f40-cc427ee8e747"
ENV OPENAI_API_KEY="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"

# Expose port for runner service
EXPOSE 7860

# Start the bot runner server
CMD ["python", "/app/runner/bot_runner.py", "--host", "0.0.0.0", "--port", "7860", "--reload"]

