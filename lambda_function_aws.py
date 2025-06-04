import boto3
import botocore.config
import json
from datetime import datetime

def generate_blog_content(topic: str) -> str:
    """
    Generates a blog article based on the provided topic using Amazon Bedrock.
    """
    instruction_prompt = f"""<s>[INST]Human: Write a 200 words blog on the topic {topic}
    Assistant:[/INST]
    """

    payload = {
        "prompt": instruction_prompt,
        "max_gen_len": 512,
        "temperature": 0.6,
        "top_p": 0.9
    }

    try:
        client = boto3.client(
            service_name="bedrock-runtime",
            region_name="us-east-1",
            config=botocore.config.Config(read_timeout=300, retries={'max_attempts': 3})
        )

        model_response = client.invoke_model(
            body=json.dumps(payload),
            modelId="meta.llama3-2-1b-instruct-v1:0"
        )

        result_content = model_response.get("body").read()
        parsed_response = json.loads(result_content)
        
        return parsed_response.get("generation", "")

    except Exception as err:
        print(f"Blog generation failed: {err}")
        return ""


def upload_to_s3(bucket: str, key: str, content: str) -> None:
    """
    Uploads the generated blog content to an S3 bucket under the specified key.
    """
    try:
        s3_client = boto3.client("s3")
        s3_client.put_object(Bucket=bucket, Key=key, Body=content)
        print("Successfully uploaded to S3.")
    except Exception as err:
        print(f"Failed to upload blog to S3: {err}")


def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Receives a blog topic, generates content, and stores it in S3.
    """
    try:
        event_body = json.loads(event.get("body", "{}"))
        topic = event_body.get("blog_topic", "")

        if not topic:
            return {
                'statusCode': 400,
                'body': json.dumps('Missing blog topic.')
            }

        blog_output = generate_blog_content(topic)

        if blog_output:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            s3_key_path = f"generated-blogs/{timestamp}.txt"
            s3_bucket_name = "mlflowarnav"

            upload_to_s3(bucket=s3_bucket_name, key=s3_key_path, content=blog_output)
        else:
            print("No blog content was returned by the model.")

        return {
            'statusCode': 200,
            'body': json.dumps('Blog generation process completed.')
        }

    except Exception as error:
        print(f"Lambda execution error: {error}")
        return {
            'statusCode': 500,
            'body': json.dumps('An error occurred during blog processing.')
        }
