import uvicorn


if __name__ == "__main__":
    uvicorn.run("support_rag_bot.web_demo:app", host="127.0.0.1", port=8080, reload=False)
