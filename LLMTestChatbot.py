# coding: utf-8
import gradio as gr
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import PyPDFLoader

import os
import fitz  # 处理PDF
from PIL import Image

# 在此处直接设置 OpenAI API Key
OPENAI_API_KEY = ("sk-proj-6nSZCYo7M55BRPpdPWzWc5WvET27PnW6bfPalM8n"
                  "-UPce8IKSUP6sJxVmXT3BlbkFJQ1ZZro2cCGJCD8n_Hx6eqtDBzOpdji-c88q6omiarjNBVVnM10mZ0oO0EA")  #
# 替换为你的OpenAI API Key


def add_text(history, text: str):
    if not text:
        raise gr.Error("请输入文本")
    history = history + [(text, "")]
    return history


class chatbot:
    def __init__(self) -> None:
        self.api_key = OPENAI_API_KEY
        self.chain = None
        self.chat_history = []
        self.page_num: int = 0
        self.count: int = 0

    def __call__(self, file: str):
        if self.count == 0:
            self.chain = self.build_conversation_chain(file)
            self.count += 1
        return self.chain

    def process_file(self, file: str):
        loader = PyPDFLoader(file.name)
        documents = loader.load()
        # 使用 os.path.basename 而不是正则表达式来提取文件名
        file_name = os.path.basename(file.name)
        return documents, file_name

    def build_conversation_chain(self, file):
        if "OPENAI_API_KEY" not in os.environ:
            raise gr.Error("OpenAI key不存在，请上传")
        documents, file_name = self.process_file(file)

        embedding_model = OpenAIEmbeddings(openai_api_key=self.api_key)
        vectorstore = FAISS.from_documents(documents=documents, embedding=embedding_model)

        chain = ConversationalRetrievalChain.from_llm(
            llm=ChatOpenAI(temperature=0.0, openai_api_key=self.api_key),
            retriever=vectorstore.as_retriever(search_kwargs={"k": 1}),
            return_source_documents=True,
        )
        return chain


def generate_response(history, query, file):
    if not file:
        raise gr.Error(message="上传一个PDF文档")

    chain = app(file)

    result = chain({"question": query, "chat_history": app.chat_history}, return_only_outputs=True)

    app.chat_history += [(query, result["answer"])]
    app.page_num = list(result["source_documents"][0])[1][1]["page"]

    for char in result["answer"]:
        history[-1][-1] += char
        yield history, ""


def render_file(file):
    doc = fitz.open(file.name)
    page = doc[app.page_num]
    picture = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
    image = Image.frombytes("RGB", [picture.width, picture.height], picture.samples)
    return image


def render_first(file):
    document = fitz.open(file)
    page = document[0]
    picture = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
    image = Image.frombytes("RGB", [picture.width, picture.height], picture.samples)
    return image, []


app = chatbot()

# 参考官网链接：https://www.gradio.app/guides/creating-a-chatbot-fast
with gr.Blocks() as demo:
    with gr.Column():
        with gr.Row():
            # 创建一个聊天界面
            chatbot = gr.Chatbot(value=[], elem_id="chatbot", height=600)
            # 创建一个图像组件，供用户查看上传的PDF文件的某一页的渲染。
            show_file = gr.Image(label="上传PDF", height=630)

    with gr.Row():
        with gr.Column(scale=6):
            txt = gr.Textbox(show_label=False, placeholder="请输入文本", container=False)

        with gr.Column(scale=2):
            submit_button = gr.Button("提交")

        with gr.Column(scale=2):
            button = gr.UploadButton("上传一个PDF文档", file_types=[".pdf"])

    # 上传 pdf，outputs定义了哪些组件会被这个函数的返回值更新
    button.upload(fn=render_first, inputs=[button], outputs=[show_file, chatbot])

    # 提交text，生成回答
    submit_button.click(
        fn=add_text, inputs=[chatbot, txt], outputs=[chatbot], queue=True, concurrency_limit=1
    ).success(
        fn=generate_response, inputs=[chatbot, txt, button], outputs=[chatbot, txt], concurrency_limit=1
    ).success(
        fn=render_file, inputs=[button], outputs=[show_file], concurrency_limit=1
    )

demo.queue().launch(share=False, max_threads=1)
