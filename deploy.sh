
set -e

docker build --platform linux/amd64 -t gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0 .

docker push gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0

gcloud run deploy fb-ai-prospecting-container\
  --image gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0 \
  --cpu 4 \
  --memory 4Gi \
  --region us-central1 \
  --platform managed \
  --timeout 300s \
  --concurrency 5 \
  --max-instances 20 \
  --min-instances 1 \
  --allow-unauthenticated

















