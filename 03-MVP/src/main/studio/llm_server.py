from langchain_openai import ChatOpenAI
llm_server = ChatOpenAI(
    # model="local-model",
    model = "deepseek-r1-distill-llama-8b",
    base_url="http://localhost:8081/v1",
    api_key="lm-studio",
    temperature=0.14,
    disable_streaming=True,
)
