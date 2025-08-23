# AWS Bedrock Blog Generators (Vanilla + RAG) — Mono-Repo

This repository contains two AWS Lambda projects that generate blog posts using Amazon Bedrock and store the outputs in Amazon S3. The functions can be triggered via an API client (e.g., Postman) through API Gateway.

1. **Project A — Simple Blog Generator (Vanilla LLM)**  
   - Lambda function that takes a `blog_topic`, calls a Bedrock foundation model, and uploads the generated text to S3.  
   - File: `lambda_simple_blog.py`

2. **Project B — RAG vs. Vanilla Comparator**  
   - Lambda function that can run **vanilla** generation *and/or* **RAG** (via Bedrock Knowledge Bases), records timings, persists artifacts (JSON, Markdown, optional `.diff`) to S3, and returns a compact API response.  
   - File: `lambda_rag_compare.py`

---

## Features

- **Bedrock integration** 
- **Vanilla vs. RAG** comparison 
- **S3 artifacting** for all outputs
- **Compact JSON API responses**
- **Environment variable configuration**

---

Example Postman POST request: providing a blog topic in raw JSON and receiving a Bedrock RAG response with citations:
![alt text](rag.png)


Generated blog stored in s3 bucket in .md format:
![alt text](image.png)

<img width="1902" height="843" alt="image" src="https://github.com/user-attachments/assets/7f1af5f2-b88f-402b-8fb3-5109429369e9" />
