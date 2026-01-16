
set -e

docker build --platform linux/amd64 -t gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0-test .

docker push gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0-test

gcloud run deploy fb-ai-prospecting-container-test\
  --image gcr.io/funnelbud-data-enricher/fb_ai_prospecting:v1.0-test \
  --cpu 6 \
  --memory 4Gi \
  --region us-central1 \
  --platform managed \
  --concurrency 20 \
  --max-instances 20 \
  --min-instances 1 \
  --allow-unauthenticated

















