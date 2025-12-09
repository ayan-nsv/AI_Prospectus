import uvicorn
import os

if __name__ == "__main__":
    # Cloud Run sets the PORT environment variable
    port = int(os.getenv("PORT", 8080))
    host = "0.0.0.0"  # Must listen on all interfaces in Cloud Run

    print(f"Starting Company Data API server on {host}:{port}")
    print("Available endpoints:")
    print(f"  - GET http://{host}:{port}/")
    print(f"  - GET http://{host}:{port}/org-number?query=<company_name_or_email>")
    print(f"  - GET http://{host}:{port}/company-data?query=<company_name_or_email>")
    print(f"  - GET http://{host}:{port}/health")
    print("\nPress Ctrl+C to stop the server")

    try:
        uvicorn.run("app:app", host=host, port=port, reload=False)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Error starting server: {e}")
