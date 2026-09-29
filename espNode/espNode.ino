#include <NimBLEDevice.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>


// MINE SAFETY MESH - NODE 001
// PHASE 2: PACKET PROTOCOL + DHT11


#define NODE_ID "NODE_001"

#define SOS_PIN 4

#define DHT_PIN 16
#define DHT_TYPE DHT11



// OLED CONFIGURATION


#define OLED_SDA  21
#define OLED_SCL  22

#define OLED_WIDTH  128
#define OLED_HEIGHT 64

#define OLED_ADDRESS 0x3C



// PROTOCOL CONFIGURATION


#define PROTOCOL_VERSION 1

#define TYPE_SOS       "SOS"
#define TYPE_STATUS    "STATUS"

#define PRIORITY_NORMAL     0
#define PRIORITY_WARNING    1
#define PRIORITY_CRITICAL   2
#define PRIORITY_EMERGENCY  3

#define DEFAULT_TTL 10


// BLE UUIDs


#define SERVICE_UUID \
    "12345678-1234-5678-1234-56789abcdef0"

#define SOS_UUID \
    "12345678-1234-5678-1234-56789abcdef1"


// GLOBAL VARIABLES


NimBLECharacteristic* sosCharacteristic = nullptr;


// SEQUENCE NUMBER


unsigned long sequenceNumber = 0;


// SOS BUTTON
// ============================================================

bool lastButtonState = HIGH;
bool stableButtonState = HIGH;

unsigned long lastDebounceTime = 0;

const unsigned long DEBOUNCE_DELAY = 50;


// HEARTBEAT
// ============================================================

unsigned long lastHeartbeatTime = 0;

const unsigned long HEARTBEAT_INTERVAL = 5000;


// DHT11
// ============================================================

DHT dht(DHT_PIN, DHT_TYPE);

const unsigned long DHT_READ_INTERVAL = 2000;

unsigned long lastDHTReadTime = 0;

float currentTemperature = NAN;
float currentHumidity = NAN;


// OLED DISPLAY
// ============================================================

Adafruit_SSD1306 display(
    OLED_WIDTH,
    OLED_HEIGHT,
    &Wire,
    -1
);

bool oledAvailable = false;
bool localSOSActive = false;

unsigned long lastOLEDUpdate = 0;

const unsigned long OLED_UPDATE_INTERVAL = 100;


// BLE RECONNECTION STATE
// ============================================================

bool bleClientConnected = false;
bool bleRestartAdvertising = false;


// BLE SERVER CALLBACKS
// ============================================================

class ServerCallbacks : public NimBLEServerCallbacks
{
public:

    void onConnect(NimBLEServer* server)
    {
        bleClientConnected = true;

        Serial.println();
        Serial.println("--------------------------------");
        Serial.println("BLE CLIENT CONNECTED");
        Serial.println("--------------------------------");
        Serial.println();
    }


    void onDisconnect(NimBLEServer* server)
    {
        bleClientConnected = false;
        bleRestartAdvertising = true;

        Serial.println();
        Serial.println("--------------------------------");
        Serial.println("BLE CLIENT DISCONNECTED");
        Serial.println("Advertising restart scheduled.");
        Serial.println("--------------------------------");
        Serial.println();
    }
};


// CREATE PACKET
// ============================================================

String createPacket(
    const char* type,
    int priority
)
{
    sequenceNumber++;

    String packet = "{";

    packet += "\"v\":";
    packet += String(PROTOCOL_VERSION);

    packet += ",\"type\":\"";
    packet += type;
    packet += "\"";

    packet += ",\"origin\":\"";
    packet += NODE_ID;
    packet += "\"";

    packet += ",\"sender\":\"";
    packet += NODE_ID;
    packet += "\"";

    packet += ",\"seq\":";
    packet += String(sequenceNumber);

    packet += ",\"priority\":";
    packet += String(priority);

    packet += ",\"ttl\":";
    packet += String(DEFAULT_TTL);

    packet += ",\"hops\":0";

    packet += ",\"time_ms\":";
    packet += String(millis());


    // --------------------------------------------------------
    // Add DHT11 data only to STATUS packets
    // --------------------------------------------------------

    if (
        strcmp(type, TYPE_STATUS) == 0 &&
        !isnan(currentTemperature) &&
        !isnan(currentHumidity)
    )
    {
        packet += ",\"temperature_c\":";
        packet += String(currentTemperature, 1);

        packet += ",\"humidity_percent\":";
        packet += String(currentHumidity, 1);
    }


    packet += "}";

    return packet;
}


// SEND PACKET
// ============================================================

void sendPacket(String packet)
{
    if (sosCharacteristic == nullptr)
    {
        Serial.println(
            "ERROR: BLE characteristic is not initialized."
        );

        return;
    }


    Serial.println();
    Serial.println("========================================");
    Serial.println("PACKET GENERATED");
    Serial.println("========================================");

    Serial.print("Packet: ");
    Serial.println(packet);

    Serial.println("========================================");


    // --------------------------------------------------------
    // Store packet in BLE characteristic
    // --------------------------------------------------------

    sosCharacteristic->setValue(
        packet.c_str()
    );


    // --------------------------------------------------------
    // Notify Raspberry Pi
    // --------------------------------------------------------

    Serial.print("[DIAG] BLE NOTIFY START... ");

    bool result =
        sosCharacteristic->notify();

    Serial.println(
        result ? "OK" : "FAILED"
    );

    Serial.println("BLE notification attempted.");
    Serial.println();
}


// SEND SOS
// ============================================================

void sendSOS()
{
    Serial.println();
    Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    Serial.println("!!!          SOS BUTTON PRESSED      !!!");
    Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");


    // --------------------------------------------------------
    // Create emergency packet
    // --------------------------------------------------------

    String packet =
        createPacket(
            TYPE_SOS,
            PRIORITY_EMERGENCY
        );


    // --------------------------------------------------------
    // Diagnostics
    // --------------------------------------------------------

    Serial.println("[DIAG] SOS PACKET CREATED");

    Serial.print("[DIAG] SOS PACKET JSON: ");
    Serial.println(packet);

    Serial.print("[DIAG] SOS PACKET LENGTH: ");
    Serial.println(packet.length());


    // IMPORTANT:
    // We intentionally do NOT use
    //
    // NimBLEDevice::getConnectedCount()
    //
    // because that API does not exist in the installed
    // NimBLE-Arduino version.
    //
    // We simply attempt the notification and report whether
    // notify() itself succeeds.

    Serial.println(
        "[DIAG] BLE CONNECTION STATE: "
        "CHECKING THROUGH NOTIFY"
    );


    // --------------------------------------------------------
    // Send packet
    // --------------------------------------------------------

    Serial.println("[DIAG] BLE NOTIFY START");

    sendPacket(packet);

    Serial.println("[DIAG] BLE NOTIFY COMPLETE");


    // --------------------------------------------------------
    // Give BLE stack time to complete notification
    // before the next loop iteration / heartbeat.
    // --------------------------------------------------------

    delay(100);

    Serial.println("[DIAG] SOS TRANSMISSION COMPLETE");
    Serial.println();
}


// SEND STATUS / HEARTBEAT
// ============================================================

void sendHeartbeat()
{
    String packet =
        createPacket(
            TYPE_STATUS,
            PRIORITY_NORMAL
        );

    sendPacket(packet);
}


// READ DHT11
// ============================================================

void readDHT11()
{
    float humidity =
        dht.readHumidity();

    float temperature =
        dht.readTemperature();


    if (
        isnan(humidity) ||
        isnan(temperature)
    )
    {
        Serial.println(
            "DHT11 read failed."
        );

        return;
    }


    currentTemperature =
        temperature;

    currentHumidity =
        humidity;


    Serial.print("DHT11: ");

    Serial.print(
        currentTemperature,
        1
    );

    Serial.print(" C, ");

    Serial.print(
        currentHumidity,
        1
    );

    Serial.println(" %");
}


// OLED INITIALIZATION
// ============================================================

void initOLED()
{
    Wire.begin(
        OLED_SDA,
        OLED_SCL
    );

    if (
        !display.begin(
            SSD1306_SWITCHCAPVCC,
            OLED_ADDRESS
        )
    )
    {
        Serial.println(
            "[OLED] Initialization FAILED"
        );

        oledAvailable = false;

        return;
    }

    oledAvailable = true;

    display.clearDisplay();

    display.setTextColor(SSD1306_WHITE);

    display.setTextSize(1);

    display.setCursor(20, 28);

    display.println(
        "MINE NODE"
    );

    display.setCursor(32, 40);

    display.println("001");

    display.display();

    Serial.println(
        "[OLED] Initialization successful"
    );

    Serial.println(
        "[OLED] READY"
    );
}


// OLED TEXT CENTERING HELPER
// ============================================================

void drawCenteredText(
    const char* text,
    int y,
    int textSize
)
{
    display.setTextSize(textSize);

    int16_t x1, y1;

    uint16_t w, h;

    display.getTextBounds(
        text, 0, 0,
        &x1, &y1, &w, &h
    );

    display.setCursor(
        (OLED_WIDTH - w) / 2,
        y
    );

    display.print(text);
}


// OLED NORMAL SCREEN
// ============================================================

void drawNormalScreen()
{
    display.clearDisplay();

    display.setTextColor(SSD1306_WHITE);


    // --------------------------------------------------------
    // Header: MINE NODE 001
    // --------------------------------------------------------

    drawCenteredText(
        "MINE NODE 001",
        0,
        1
    );


    // --------------------------------------------------------
    // Separator line
    // --------------------------------------------------------

    display.drawLine(
        0, 11,
        OLED_WIDTH, 11,
        SSD1306_WHITE
    );


    // --------------------------------------------------------
    // Sensor labels: TEMP and HUM
    // --------------------------------------------------------

    display.setTextSize(1);

    display.setCursor(0, 16);

    display.print("TEMP");

    display.setCursor(92, 16);

    display.print("HUM");


    // --------------------------------------------------------
    // Sensor values: large prominent numbers
    // --------------------------------------------------------

    display.setTextSize(2);

    if (
        isnan(currentTemperature)
    )
    {
        display.setCursor(0, 30);

        display.print("--.-");
    }
    else
    {
        display.setCursor(0, 30);

        display.print(
            currentTemperature,
            1
        );
    }

    display.setTextSize(1);

    display.setCursor(0, 46);

    display.print("\xF7" "C");


    display.setTextSize(2);

    if (
        isnan(currentHumidity)
    )
    {
        display.setCursor(78, 30);

        display.print("--.-");
    }
    else
    {
        display.setCursor(78, 30);

        display.print(
            currentHumidity,
            1
        );
    }

    display.setTextSize(1);

    display.setCursor(78, 46);

    display.print("%");


    // --------------------------------------------------------
    // Bottom status line
    // --------------------------------------------------------

    display.setCursor(0, 56);

    display.print("\x07");

    display.setCursor(10, 56);

    display.print("SENSOR ONLINE");


    display.display();
}


// OLED SOS SCREEN
// ============================================================

void drawSOSScreen()
{
    display.clearDisplay();

    display.setTextColor(SSD1306_WHITE);


    // --------------------------------------------------------
    // Flashing border: toggle every 500ms
    // Non-blocking: uses millis()
    // --------------------------------------------------------

    bool flashOn =
        ((millis() / 500) % 2 == 0);


    // --------------------------------------------------------
    // Border
    // --------------------------------------------------------

    if (flashOn)
    {
        display.drawRect(
            0, 0,
            OLED_WIDTH, OLED_HEIGHT,
            SSD1306_WHITE
        );
    }
    else
    {
        display.drawRoundRect(
            2, 2,
            OLED_WIDTH - 4,
            OLED_HEIGHT - 4,
            3,
            SSD1306_WHITE
        );
    }


    // --------------------------------------------------------
    // !!! SOS !!! header
    // --------------------------------------------------------

    drawCenteredText(
        "!!! SOS !!!",
        6,
        1
    );


    // --------------------------------------------------------
    // SOS - very large centered
    // --------------------------------------------------------

    drawCenteredText(
        "SOS",
        20,
        3
    );


    // --------------------------------------------------------
    // EMERGENCY label
    // --------------------------------------------------------

    drawCenteredText(
        "EMERGENCY",
        46,
        1
    );


    // --------------------------------------------------------
    // NODE ID
    // --------------------------------------------------------

    drawCenteredText(
        "NODE 001",
        54,
        1
    );


    display.display();
}


// OLED UPDATE (non-blocking)
// ============================================================

void updateOLED(unsigned long now)
{
    if (!oledAvailable)
    {
        return;
    }


    if (
        (now - lastOLEDUpdate)
        < OLED_UPDATE_INTERVAL
    )
    {
        return;
    }

    lastOLEDUpdate = now;


    if (localSOSActive)
    {
        drawSOSScreen();
    }
    else
    {
        drawNormalScreen();
    }
}


// SETUP
// ============================================================

void setup()
{
    // --------------------------------------------------------
    // SERIAL
    // --------------------------------------------------------

    Serial.begin(115200);

    delay(500);


    // --------------------------------------------------------
    // SOS BUTTON
    // --------------------------------------------------------

    pinMode(
        SOS_PIN,
        INPUT_PULLUP
    );


    // --------------------------------------------------------
    // DHT11
    // --------------------------------------------------------

    dht.begin();


    // --------------------------------------------------------
    // OLED DISPLAY
    // --------------------------------------------------------

    initOLED();


    // --------------------------------------------------------
    // STARTUP INFORMATION
    // --------------------------------------------------------

    Serial.println();
    Serial.println("==============================");
    Serial.println("     UNDERGROUND MINE NODE");
    Serial.println("==============================");

    Serial.print("Node ID: ");
    Serial.println(NODE_ID);

    Serial.print("Protocol Version: ");
    Serial.println(PROTOCOL_VERSION);

    Serial.print("Default TTL: ");
    Serial.println(DEFAULT_TTL);

    Serial.print("SOS GPIO: ");
    Serial.println(SOS_PIN);

    Serial.print("DHT GPIO: ");
    Serial.println(DHT_PIN);

    Serial.println();


    // --------------------------------------------------------
    // Check initial button state
    // --------------------------------------------------------

    Serial.print(
        "Initial SOS button state: "
    );

    if (
        digitalRead(SOS_PIN) == HIGH
    )
    {
        Serial.println(
            "RELEASED"
        );
    }
    else
    {
        Serial.println(
            "PRESSED"
        );
    }


    // ========================================================
    // BLE INITIALIZATION
    // ========================================================

    NimBLEDevice::init(
        NODE_ID
    );


    NimBLEServer* server =
        NimBLEDevice::createServer();


    server->setCallbacks(
        new ServerCallbacks()
    );


    // Automatically restart advertising
    // when Raspberry Pi disconnects

    server->advertiseOnDisconnect(
        true
    );


    // ========================================================
    // BLE SERVICE
    // ========================================================

    NimBLEService* service =
        server->createService(
            SERVICE_UUID
        );


    // ========================================================
    // SOS / PACKET CHARACTERISTIC
    // ========================================================

    sosCharacteristic =
        service->createCharacteristic(
            SOS_UUID,

            NIMBLE_PROPERTY::READ |
            NIMBLE_PROPERTY::NOTIFY
        );


    // Initial packet

    sosCharacteristic->setValue(
        "{\"v\":1,\"type\":\"STATUS\",\"origin\":\"NODE_001\",\"sender\":\"NODE_001\",\"seq\":0,\"priority\":0,\"ttl\":10,\"hops\":0,\"time_ms\":0}"
    );


    // Start service

    service->start();


    // ========================================================
    // BLE ADVERTISING
    // ========================================================

    NimBLEAdvertising* advertising =
        NimBLEDevice::getAdvertising();


    advertising->setName(
        NODE_ID
    );


    advertising->addServiceUUID(
        SERVICE_UUID
    );


    advertising->enableScanResponse(
        true
    );


    advertising->start();


    // ========================================================
    // READY
    // ========================================================

    Serial.println();
    Serial.println(
        "BLE advertising started."
    );

    Serial.println(
        "Waiting for Raspberry Pi..."
    );

    Serial.println();

    Serial.println("==============================");
    Serial.println("          NODE READY");
    Serial.println("==============================");
    Serial.println();
}


// MAIN LOOP
// ============================================================

void loop()
{
    unsigned long now =
        millis();


    // ========================================================
    // SOS BUTTON
    // ========================================================

    bool reading =
        digitalRead(SOS_PIN);


    // --------------------------------------------------------
    // Detect electrical state change
    // --------------------------------------------------------

    if (
        reading != lastButtonState
    )
    {
        lastDebounceTime =
            now;

        lastButtonState =
            reading;
    }


    // --------------------------------------------------------
    // Wait for debounce period
    // --------------------------------------------------------

    if (
        (now - lastDebounceTime)
        >= DEBOUNCE_DELAY
    )
    {
        if (
            reading != stableButtonState
        )
        {
            stableButtonState =
                reading;


            // ------------------------------------------------
            // BUTTON PRESSED
            // ------------------------------------------------

            if (
                stableButtonState == LOW
            )
            {
                localSOSActive = true;

                Serial.println(
                    "[OLED] SOS MODE"
                );

                Serial.println(
                    "[DIAG] SOS BUTTON DEBOUNCED LOW - calling sendSOS()"
                );

                sendSOS();
            }


            // ------------------------------------------------
            // BUTTON RELEASED
            // ------------------------------------------------

            else
            {
                Serial.println(
                    "SOS button released."
                );
            }
        }
    }


    // ========================================================
    // DHT11
    // ========================================================

    if (
        now - lastDHTReadTime
        >= DHT_READ_INTERVAL
    )
    {
        lastDHTReadTime =
            now;

        readDHT11();
    }


    // ========================================================
    // HEARTBEAT
    // ========================================================

    if (
        now - lastHeartbeatTime
        >= HEARTBEAT_INTERVAL
    )
    {
        lastHeartbeatTime =
            now;

        sendHeartbeat();
    }


    // ========================================================
    // OLED DISPLAY
    // ========================================================

    updateOLED(now);


    // ========================================================
    // BLE ADVERTISING RESTART
    // ========================================================

    if (bleRestartAdvertising)
    {
        bleRestartAdvertising = false;

        NimBLEDevice::startAdvertising();

        Serial.println(
            "[BLE] Advertising restarted"
        );
    }


    // ========================================================
    // SMALL LOOP DELAY
    // ========================================================

    delay(5);
}