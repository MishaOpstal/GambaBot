FROM python:3.12-slim
LABEL authors="Misha Opstal"

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py .
COPY config.py .
COPY database.py .
COPY cogs ./cogs
COPY helpers ./helpers

# Set environment variable
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "bot.py"]