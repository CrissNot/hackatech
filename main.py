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


    def send_message(self, data, startmonth, endmonth, anio):
        prompt = f"""
Rol: Eres un profesional experto en proyectos de energía renovable y tienes amplios conocimientos en predicción temporales

Task: 
necesito que generes una predicción precisa de los valores de GHI para el año **{anio}, específicamente en el rango de meses comprendido entre *{startmonth} y {endmonth}*.

Formato de salida:
Tu predicción debe cumplir con los siguientes criterios:

1. Objetivo principal: Predecir los valores promedio mensuales de GHI (en kWh/m²/día) para cada mes en el rango especificado de {anio}.
2. Entrada: Utiliza los valores históricos del año 2023 contenidos en el JSON {data['historical_data']} como única fuente de entrenamiento.
3. Formato de salida: La predicción debe devolverse exclusivamente en el mismo formato del objeto {data['historical_data']}, eliminando el historico y generando la prediccion correspondientes al año {anio} **solo para los meses solicitados.
4. Campo adicional obligatorio: Agrega un campo al JSON llamado "metadatos_prediccion" que incluya:
   - "metodo_usado": el nombre del modelo estadístico aplicado (ej. "Prophet", "SARIMA", "Holt-Winters").
   - "margen_error_estimado": error estimado (RMSE, MAE o MAPE, según el modelo).
   - "unidad": especifica "kWh/m²/día".
   - Metrica d eprecicion del modelo en %

5. Modelos recomendados: Evalúa e implementa al menos uno de los siguientes enfoques:
   - Modelos clásicos de series temporales como Holt-Winters.
 
Recompensa:
Si realizas correctamente la tarea, te consideraremos un experto / genio en energías renovables y te otorgaremos una bonificación

Refuerzo:
La respuesta debe consistir exclusivamente en un JSON válido con los valores de GHI predichos para el rango solicitado de 2025, más los metadatos mencionados

Nuevamente recuerda y ten presente que no debes devolverme el mismo json que te estamos entregando, sino, que tienes que realizar la respectiva predicción real aplicando el metodo Hunt winters

Te recuerdo que no puedes responder con mas que con el json
"""

        response = self.model.generate_content(prompt)
        return response.text



if __name__ == '__main__':
    from endpoints import Enpoints

    app = Enpoints()
    #app.send_message()
    uvicorn.run(app.app, host="0.0.0.0", port=8000)