import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiomqtt import Client, MqttError

app = FastAPI()

# Configurazione (Usa variabili d'ambiente per Azure!)
MQTT_HOST = "192.168.1.12" #"tuo-broker-azure.messaging.azure.com"
MQTT_PORT = 1883 #8883
COMMAND_TOPIC = "iot/command/led"
STATUS_TOPIC = "iot/status/led"

origins = [
    "https://thankful-stone-0131f1503.2.azurestaticapps.net"
    "http://localhost:8080",
    "http://192.168.1.8:8080",
    "http://192.168.1.12:8080",
#    "https://gentle-ocean-123.azurestaticapps.net", # Il tuo frontend in produzione
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # Quali domini possono chiamare?
    allow_credentials=True,
    allow_methods=["*"],             # Permette GET, POST, PUT, DELETE, OPTIONS, ecc.
    allow_headers=["*"],             # Permette tutti gli header (es. Content-Type, Authorization)
)

# 1. Gestore delle connessioni WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# 2. Task in background per ascoltare MQTT
async def mqtt_listen():
    """Ascolta i messaggi dal dispositivo e li invia ai WebSocket"""
    try:
        async with Client(MQTT_HOST, port=MQTT_PORT) as client:
            await client.subscribe(STATUS_TOPIC)
            async for message in client.messages:
                payload = message.payload.decode()
                # Inviamo lo stato del device a TUTTI i frontend connessi
                await manager.broadcast(json.dumps({"state": payload}))
    except MqttError:
        print("Errore di connessione MQTT. Riprovo tra 5 secondi...")
        await asyncio.sleep(5)
        await mqtt_listen()

# Avvia il task MQTT all'avvio di FastAPI
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(mqtt_listen())

# 3. Endpoint WebSocket per il Frontend
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Opzionale: riceve comandi via WS
            data = await websocket.receive_text()
            # ... logica per inviare comandi via MQTT ...
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 4. Endpoint REST (PUT) per cambiare stato
@app.put("/api/command")
async def change_state(payload: dict):
    print(f"received: {payload}")
    new_state = payload.get("command")
    async with Client(MQTT_HOST, port=MQTT_PORT) as client:
        await client.publish(COMMAND_TOPIC, payload=new_state)
    return {"status": "comando inviato"}
