import google.generativeai as geminis
from dotenv import load_dotenv
import os
import uvicorn
import pandas as pd

class Gemini():
    def __init__(self):
        load_dotenv()
        self.secret_key = os.getenv("GEMINIS_API_KEY")
        geminis.configure(api_key=self.secret_key)
        self.model = geminis.GenerativeModel("gemini-1.5-flash")


    def send_message(self, data, startmonth, endmonth):

        prompt = f"""Teniendo en cuenta la siguiente información, la cual representa los valores históricos de GHI (Global Horizontal Irradiance) del municipio **{data['municipality']}** para los meses de **ENERO a DICIEMBRE de 2024**, necesito que generes una predicción precisa de los valores de GHI para el año **2025**, específicamente en el rango de meses comprendido entre **{startmonth}** y **{endmonth}**.

Tu predicción debe cumplir con los siguientes criterios:

1. **Objetivo principal**: Predecir los valores promedio mensuales de GHI (en kWh/m²/día) para cada mes en el rango especificado de 2025.
2. **Entrada**: Utiliza los valores históricos del año 2024 contenidos en el JSON `{data}` como única fuente de entrenamiento.
3. **Formato de salida**: La predicción debe devolverse exclusivamente en el mismo formato del objeto `{data}`, reemplazando los valores de GHI con las predicciones correspondientes al año 2025 **solo para los meses solicitados**.
4. **Campo adicional obligatorio**: Agrega un campo al JSON llamado `"metadatos_prediccion"` que incluya:
   - `"metodo_usado"`: el nombre del modelo estadístico aplicado (ej. `"Prophet"`, `"SARIMA"`, `"Holt-Winters"`).
   - `"margen_error_estimado"`: error estimado (RMSE, MAE o MAPE, según el modelo).
   - `"unidad"`: especifica `"kWh/m²/día"`.
   - Metrica d eprecicion del modelo en %

5. **Modelos recomendados**: Evalúa e implementa al menos uno de los siguientes enfoques:
   - Modelos clásicos de series temporales como **ARIMA**, **SARIMA**, o **Holt-Winters**.
   - Alternativamente, puedes utilizar **Prophet** (Meta/Facebook) si mejora la precisión de la predicción.

La respuesta debe consistir exclusivamente en un **JSON válido** con los valores de GHI predichos para el rango solicitado de 2025, más los metadatos mencionados.

---

### Ejemplo de estructura esperada:

{data}"""

        response = self.model.generate_content(prompt)
        print(response.text)


    def read_file(self):
        df = pd.read_csv("file.csv")
        df_filtrado = df[["Municipio", "Departamento", "Latitud", "Longitud"]]
        print(df_filtrado.drop_duplicates())




if __name__ == '__main__':
    from endpoints import Enpoints

    app = Enpoints()
    #app.send_message()
    uvicorn.run(app.app, host="0.0.0.0", port=8000)