from fastapi import FastAPI
import google.generativeai as geminis
from dotenv import load_dotenv
import os
import pandas as pd


class Gemini():
    def __init__(self):
        load_dotenv()
        self.secret_key = os.getenv("GEMINIS_API_KEY")
        print(self.secret_key)
        geminis.configure(api_key=self.secret_key)
        self.model = geminis.GenerativeModel("gemini-1.5-flash")


    def send_message(self):
        response = self.model.generate_content("Dame un resumen de qué es la API de Gemini")
        print(response.text)


    def read_file(self):
        df = pd.read_csv("file.csv")
        df_filtrado = df[["Municipio", "Departamento", "Latitud", "Longitud"]]
        print(df_filtrado.drop_duplicates())




if __name__ == '__main__':
    app = Gemini()
    #app.send_message()
    app.read_file()