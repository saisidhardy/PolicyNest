# Multi-stage production container for PolicyNest
FROM python:3.12-slim

WORKDIR /app

# Copy dependency specifications and install Python requirements
COPY policynest_mvp/copilot_api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure production build of the frontend exists
RUN python policynest_mvp/build_site.py --mode prod

ENV PORT=8000
ENV POLICYNEST_ENV=production
ENV DATA_DIR=/data

EXPOSE 8000

CMD ["python", "server.py"]
