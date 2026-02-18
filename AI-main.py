import os  # Для путей и проверки файлов
import sys  # Для sys.exit при ошибках
import json  # Для парсинга результатов Vosk
import pyaudio  # Для захвата аудио с микрофона
from vosk import Model, KaldiRecognizer  # Для оффлайн распознавания речи
import pyttsx3  # Для оффлайн синтеза речи (TTS)
import time  # Для тайминга загрузки
from datetime import datetime  # Для команд с временем/датой

# ================================================
# Шаг 1: Настройка путей (динамические, работают в Spyder, cmd, exe)
# ================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # Папка, где лежит bot.py
MODEL_PATH = os.path.join(SCRIPT_DIR, "model", "vosk-model-ru-0.22")  # Путь к модели Vosk — измени, если папка другая

SAMPLE_RATE = 16000  # Стандарт для Vosk
CHUNK_SIZE = 4000  # Уменьшили для лучшей отзывчивости (было 8000, чтобы избежать overflow)

# Параметры подавления собственного голоса ассистента
LAST_BOT_PHRASE = ""           # Последняя фраза, которую произнёс ассистент
LAST_BOT_END_TIME = 0.0        # Время окончания произнесения фразы
IGNORE_WINDOW_SEC = 1.5        # Окно (в секундах), в течение которого мы игнорируем свою речь

# Шаг 2: Проверка модели Vosk (чтобы избежать ошибок загрузки)
critical_file = os.path.join(MODEL_PATH, "am", "final.mdl")
if not os.path.exists(critical_file):
    print("Ошибка: модель не найдена по пути:", MODEL_PATH)
    print("Содержимое папки проекта:", os.listdir(SCRIPT_DIR))
    sys.exit(1)

print("Загружаю модель Vosk... ", end="", flush=True)
start = time.time()
try:
    model = Model(MODEL_PATH)
    print(f"OK ({time.time() - start:.1f} сек)")
except Exception as e:
    print(f"Ошибка загрузки модели: {e}")
    sys.exit(1)

rec = KaldiRecognizer(model, SAMPLE_RATE)  # Инициализация распознавателя
rec.SetWords(True)  # Возвращать слова с вероятностями (опционально)

# ================================================
# Шаг 3: Функция speak с переинициализацией (фикс "засыпания" TTS)
# ================================================
def speak(text):
    """Озвучивание ответа ассистента с запоминанием того, что было сказано."""
    global LAST_BOT_PHRASE, LAST_BOT_END_TIME

    print(f"J.A.R.V.I.S говорит: {text}")
    try:
        # Переинициализируем pyttsx3 перед каждым вызовом — это решает проблему, когда голос "молчит" после первого раза
        engine = pyttsx3.init()
        engine.setProperty('rate', 140)  # Скорость (чтобы звучал как JARVIS)
        engine.setProperty('volume', 1.0)  # Громкость максимум

        # Безопасный выбор голоса Aleksandr (RHVoice) / русского голоса
        voices = engine.getProperty('voices')
        selected = False
        for voice in voices:
            if "aleksandr" in voice.name.lower():
                engine.setProperty('voice', voice.id)
                selected = True
                break

        if not selected:
            # Fallback на любой русский голос (учитываем, что voice.languages может не существовать
            # или содержать байты, из-за чего раньше могла быть ошибка и TTS полностью "молчал")
            for voice in voices:
                try:
                    langs = getattr(voice, "languages", [])
                    normalized_langs = []
                    for lang in langs:
                        if isinstance(lang, bytes):
                            try:
                                normalized_langs.append(lang.decode("utf-8").lower())
                            except Exception:
                                continue
                        else:
                            normalized_langs.append(str(lang).lower())

                    if any("ru" in lang for lang in normalized_langs) or "russian" in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                except Exception as e:
                    print(f"Ошибка при выборе голоса: {e}")
                    continue

        engine.say(text)
        engine.runAndWait()
        engine.stop()  # Принудительный стоп, чтобы очистить буфер
        time.sleep(0.1)  # Лёгкая пауза, чтобы не прерывать следующий захват микрофона

        # Запоминаем, что именно и когда ассистент сказал — чтобы потом игнорировать эту речь в распознавании
        LAST_BOT_PHRASE = text.strip().lower()
        LAST_BOT_END_TIME = time.time()
    except Exception as e:
        print(f"Ошибка в speak: {e}")


def is_own_speech(recognized_text: str) -> bool:
    """
    Возвращает True, если распознанный текст с высокой вероятностью
    является эхом голоса ассистента, а не пользователя.
    """
    global LAST_BOT_PHRASE, LAST_BOT_END_TIME

    recognized_text = recognized_text.strip().lower()
    if not recognized_text:
        return False

    now = time.time()

    # Фильтруем только в коротком окне после окончания фразы ассистента
    if now - LAST_BOT_END_TIME > IGNORE_WINDOW_SEC:
        return False

    if not LAST_BOT_PHRASE:
        return False

    # Простая проверка похожести: точное совпадение или подстрока
    if (
        recognized_text == LAST_BOT_PHRASE
        or recognized_text in LAST_BOT_PHRASE
        or LAST_BOT_PHRASE in recognized_text
    ):
        print(f"Игнорирую собственный голос: {recognized_text}")
        return True

    return False

# ================================================
# Шаг 4: Инициализация микрофона с отладкой
# ================================================
p = pyaudio.PyAudio()
try:
    print("Открываю микрофон...")
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )
    stream.start_stream()
    print("Микрофон OK")
except Exception as e:
    print(f"Ошибка микрофона: {e}")
    print("Проверь права доступа к микрофону в Windows (Конфиденциальность → Микрофон)")
    sys.exit(1)

# Шаг 5: Тестовый голос при запуске (чтобы проверить TTS сразу)
speak("Тест. Голос Джарвиса. Система готова.")

print("\n" + "═" * 70)
print("J.A.R.V.I.S активен. Говори команды (привет, как дела, анекдот, время, дата, стоп).")
print("Выход: Ctrl+C или 'стоп'")
print("═" * 70 + "\n")

# ================================================
# Шаг 6: Основной цикл с отладкой и обработкой ошибок
# ================================================
try:
    while True:
        print("Слушаю...")  # Отладка — показывает, что цикл живой (выводит каждые ~0.5 сек)
        try:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)  # Чтение с фиксом overflow
        except Exception as e:
            print(f"Ошибка чтения микрофона: {e}")
            continue

        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get("text", "").strip().lower()
            if text:
                # Сначала проверяем, не является ли это эхом собственного голоса
                if is_own_speech(text):
                    continue

                print(f"\nТы сказал: {text}")

                # Шаг 7: Обработка команд (расширяй здесь)
                if "привет" in text or "здравствуй" in text:
                    speak("Приветствую, сэр.")
                elif "как дела" in text or "как ты" in text:
                    speak("Всё в порядке. А у вас?")
                elif "анекдот" in text:
                    speak("Почему программисты не любят пляж? Потому что там слишком много песка, и они путают его с sandbox.")
                elif "время" in text or "который час" in text:
                    now = datetime.now().strftime("%H:%M")
                    speak(f"Сейчас {now}.")
                elif "дата" in text or "число" in text:
                    today = datetime.now().strftime("%d %B %Y года")
                    speak(f"Сегодня {today}.")
                elif "стоп" in text or "выход" in text:
                    speak("До свидания, сэр.")
                    break
                else:
                    speak("Команда принята, но пока не реализована.")

        else:
            partial = json.loads(rec.PartialResult())
            ptext = partial.get("partial", "").strip()
            if ptext:
                print(f"Частичное: {ptext}", end="\r", flush=True)

except KeyboardInterrupt:
    print("\nCtrl+C — выход")
    speak("Остановка. До свидания.")
except Exception as e:
    print(f"Критическая ошибка в цикле: {e}")

# Шаг 8: Корректное закрытие ресурсов
finally:
    speak("Система отключается.")  # Последний вызов TTS
    try:
        stream.stop_stream()
        stream.close()
        p.terminate()
    except Exception as e:
        print(f"Ошибка закрытия: {e}")
    print("J.A.R.V.I.S завершён.")