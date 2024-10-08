# llm_service.py

import os
import pandas as pd
from io import StringIO
from docx import Document as DocxDocument
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.schema import Document
import tiktoken
from settings import OPENAI_API_KEY, MODEL_NAME


class LLMService:
    def __init__(self, model_name=MODEL_NAME):
        self.llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name=model_name)
        self.vector_store = None

    def load_excel_file(self, file_path):
        data = pd.read_excel(file_path)
        text_data = StringIO()
        data.to_string(buf=text_data)
        return text_data.getvalue()

    def load_word_file(self, file_path):
        doc = DocxDocument(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    def load_and_index_documents(self, folder_path):
        documents = []
        found_valid_file = False

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)

            if filename.endswith(".pdf"):
                loader = PyMuPDFLoader(file_path)
                docs = loader.load()
                for doc in docs:
                    doc.metadata = {"source": filename}
                    documents.append(doc)
                found_valid_file = True

            elif filename.endswith(".docx"):
                content = self.load_word_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})
                documents.append(doc)
                found_valid_file = True

            elif filename.endswith(".xlsx"):
                content = self.load_excel_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})
                documents.append(doc)
                found_valid_file = True

        if not found_valid_file:
            return "No valid files found in the folder. Please provide PDF, Word, or Excel files."

        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        split_docs = text_splitter.split_documents(documents)

        embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        self.vector_store = FAISS.from_documents(split_docs, embeddings)
        return "Documents successfully indexed."

    def retrieve_and_generate(self, prompt):
        if not self.vector_store:
            return "Please set the folder path using /folder and ensure documents are loaded.", None

        retriever = self.vector_store.as_retriever()

        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=retriever,
            chain_type="stuff",
            return_source_documents=True
        )

        try:
            result = qa_chain({"query": prompt})
            sources = result.get("source_documents", [])
            if not sources:
                return result["result"], None

            source_files = set([doc.metadata["source"] for doc in sources if "source" in doc.metadata])

            response = result["result"]
            return response, source_files

        except Exception as e:
            return f"An error occurred: {str(e)}", None

    def count_tokens_in_context(self, folder_path):
        """Counts the total number of tokens in documents within a folder."""
        documents = []
        found_valid_file = False

        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)

            if filename.endswith(".pdf"):
                loader = PyMuPDFLoader(file_path)
                docs = loader.load()
                for doc in docs:
                    doc.metadata = {"source": filename}
                    documents.append(doc)
                found_valid_file = True

            elif filename.endswith(".docx"):
                content = self.load_word_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})
                documents.append(doc)
                found_valid_file = True

            elif filename.endswith(".xlsx"):
                content = self.load_excel_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})
                documents.append(doc)
                found_valid_file = True

        if not found_valid_file:
            return "No valid files found in the folder. Please provide PDF, Word, or Excel files."

        # Count tokens in the documents
        tokenizer = tiktoken.encoding_for_model('gpt-4')  # Tokenizer for the specific model

        total_tokens = 0
        for doc in documents:
            total_tokens += len(tokenizer.encode(doc.page_content))

        return total_tokens
