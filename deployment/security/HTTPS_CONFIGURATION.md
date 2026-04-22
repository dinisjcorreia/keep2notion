# HTTPS Configuration

Use HTTPS for every public entrypoint.

## Public Endpoints

Usually only these need public HTTPS:

- admin UI
- API gateway

Internal service-to-service traffic can remain private inside your cluster or network boundary.

## Recommended Shape

```text
Internet
  -> TLS terminator / ingress / reverse proxy
  -> admin_interface
  -> api_gateway
```

## Requirements

- valid TLS certificates
- domain names pointing at ingress or reverse proxy
- secure cookies enabled for public UI
- HSTS if you control long-term domain policy

## Application Notes

Django admin UI should run behind HTTPS in real deployments.

FastAPI endpoints exposed publicly should also sit behind HTTPS.

## Checklist

- certificates issued
- redirect HTTP -> HTTPS
- secure headers enabled
- cookie security reviewed
- admin URL not exposed without TLS

## Verification

```bash
curl -I https://YOUR_ADMIN_DOMAIN/
curl -I https://YOUR_API_DOMAIN/api/v1/health
```
