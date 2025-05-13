import hashlib
import json
import asyncio
import websockets
import sys
from blockchain import Blockchain, Transaction, Block
import aioconsole
from coincurve import PrivateKey

# Inicjalizacja Blockchain
blockchain = None  # Nie inicjalizujemy blockchaina na starcie
SERVER_HOST = 'localhost'  # Zmień na IP serwera jeśli łączysz się zdalnie
SERVER_PORT = 5000
websocket = None
connection_lock = asyncio.Lock()

wallets = {}

def update_balances():
    """Aktualizuje balanse na podstawie łańcucha bloków"""
    if not blockchain:  # Nie aktualizujemy jeśli nie ma blockchaina
        return
    blockchain.balances.clear()  # Wyczyść stare balanse
    
    # Przejrzyj wszystkie bloki i transakcje
    for block in blockchain.chain:
        for tx in block.transactions:
            # Konwertuj transakcję na słownik jeśli to obiekt
            if isinstance(tx, Transaction):
                tx_data = tx.to_dict()
            else:
                tx_data = tx
                
            # Odejmij od nadawcy
            if tx_data['sender'] in blockchain.balances:
                blockchain.balances[tx_data['sender']] -= tx_data['amount']
            else:
                blockchain.balances[tx_data['sender']] = -tx_data['amount']
            
            # Dodaj do odbiorcy
            if tx_data['recipient'] in blockchain.balances:
                blockchain.balances[tx_data['recipient']] += tx_data['amount']
            else:
                blockchain.balances[tx_data['recipient']] = tx_data['amount']

async def connect_to_server():
    global websocket
    try:
        print(f"[INFO] Próba połączenia z serwerem ws://{SERVER_HOST}:{SERVER_PORT}")
        websocket = await websockets.connect(
            f'ws://{SERVER_HOST}:{SERVER_PORT}',
            ping_interval=20,
            ping_timeout=None,
            close_timeout=None
        )
        print("[INFO] Połączono z serwerem")
        return True
    except Exception as e:
        print(f"[ERROR] Błąd połączenia z serwerem: {e}")
        websocket = None
        return False

async def sync_with_server():
    global websocket, blockchain
    async with connection_lock:
        if not websocket:
            print("[INFO] Brak połączenia z serwerem, próba połączenia...")
            if not await connect_to_server():
                return False
        
        try:
            print("[INFO] Wysyłanie żądania synchronizacji...")
            await websocket.send(json.dumps({'type': 'sync'}))
            print("[INFO] Oczekiwanie na odpowiedź...")
            response = await websocket.recv()
            print("[INFO] Otrzymano odpowiedź od serwera")
            payload = json.loads(response)
            if payload['type'] == 'chain':
                if not blockchain:  # Tworzymy blockchain tylko jeśli go nie ma
                    blockchain = Blockchain()
                new_chain = [Block.from_dict(b) for b in payload['data']]
                blockchain.replace_chain(new_chain)
                update_balances()  # Aktualizuj balanse po synchronizacji
                print("[INFO] Zsynchronizowano z serwerem")
                return True
        except websockets.exceptions.ConnectionClosed:
            print("[ERROR] Połączenie zostało zamknięte podczas synchronizacji")
            websocket = None
            return False
        except Exception as e:
            print(f"[ERROR] Błąd synchronizacji z serwerem: {e}")
            return False

async def send_to_server(payload):
    global websocket, blockchain
    async with connection_lock:
        if not websocket:
            print("[INFO] Brak połączenia z serwerem, próba połączenia...")
            if not await connect_to_server():
                return False
        
        try:
            print("[INFO] Wysyłanie danych do serwera...")
            await websocket.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            print("[ERROR] Połączenie zostało zamknięte podczas wysyłania danych")
            websocket = None
            return False
        except Exception as e:
            print(f"[ERROR] Błąd wysyłania danych do serwera: {e}")
            return False

def create_wallet():
    try:
        # Generuj losowy klucz prywatny
        private_key = PrivateKey()
        # Pobierz klucz publiczny
        public_key = private_key.public_key
        # Wygeneruj adres (hash z klucza publicznego)
        address = hashlib.sha256(public_key.format()).hexdigest()
        # Zapisz tylko klucz prywatny
        wallets[address] = private_key.to_hex()
        return address, private_key.to_hex()
    except Exception as e:
        print(f"[ERROR] Błąd tworzenia portfela: {e}")
        return None, None

def sign_transaction(sender_priv_hex, sender_addr, recipient, amount):
    try:
        # Konwertuj klucz prywatny z hex na PrivateKey
        private_key = PrivateKey.from_hex(sender_priv_hex)
        # Przygotuj wiadomość do podpisania
        message = f"{sender_addr}{recipient}{amount}".encode()
        # Zahashuj wiadomość do 32 bajtów
        message_hash = hashlib.sha256(message).digest()
        print(f"Message hash: {message_hash.hex()}, length: {len(message_hash)}")
        # Podpisz zahashowaną wiadomość
        signature = private_key.sign_recoverable(message_hash, hasher=None).hex()
        return signature
    except Exception as e:
        print(f"[ERROR] Błąd podpisywania transakcji: {e}")
        return None

async def listen_for_updates():
    global websocket, blockchain
    while True:
        try:
            if not websocket:
                async with connection_lock:
                    if not await connect_to_server():
                        await asyncio.sleep(5)
                        continue

            try:
                message = await websocket.recv()  # NIE blokujemy locka w tym miejscu
                payload = json.loads(message)

                if payload['type'] == 'chain':
                    async with connection_lock:  # tylko operacje na blockchain
                        if not blockchain:
                            blockchain = Blockchain()
                        new_chain = [Block.from_dict(b) for b in payload['data']]
                        blockchain.replace_chain(new_chain)
                        update_balances()
                        print("[INFO] Zaktualizowano blockchain z serwera")
                elif payload['type'] == 'pending_transactions':
                    async with connection_lock:
                        if not blockchain:
                            blockchain = Blockchain()
                        blockchain.pending_transactions = [Transaction.from_dict(tx) for tx in payload['data']]
                        print("[INFO] Zaktualizowano oczekujące transakcje")
            except websockets.exceptions.ConnectionClosed:
                print("[ERROR] Połączenie zostało zamknięte podczas nasłuchiwania")
                async with connection_lock:
                    websocket = None
            except Exception as e:
                print(f"[ERROR] Błąd podczas nasłuchiwania: {e}")
        except Exception as e:
            print(f"[ERROR] Błąd w listen_for_updates: {e}")
        await asyncio.sleep(1)

async def menu():
    global blockchain
    print("[INFO] Synchronizacja z serwerem...")
    if not await sync_with_server():
        print("[ERROR] Nie można połączyć z serwerem. Sprawdź czy serwer jest uruchomiony.")
        return
    
    asyncio.create_task(listen_for_updates())
    
    while True:
        if not blockchain:
            print("[ERROR] Brak połączenia z blockchainem, próba ponownego połączenia...")
            if not await sync_with_server():
                await asyncio.sleep(5)
                continue
                
        print("\n=== MENU ===")
        print("1. Stwórz portfel")
        print("2. Pokaż balans")
        print("3. Wykonaj transakcję")
        print("4. Wydobądź blok")
        print("5. Zobacz blockchain")
        print("6. Wyjście")
        choice = await aioconsole.ainput("> ")

        if choice == "1":
            addr, priv = create_wallet()
            if addr and priv:
                print("\n[SUKCES] Utworzono nowy portfel:")
                print("Adres:", addr)
                print("Klucz prywatny:", priv)

        elif choice == "2":
            addr = await aioconsole.ainput("Podaj adres: ")
            balance = blockchain.balances.get(addr, 0)
            print(f"\n[INFO] Balans dla adresu {addr}: {balance}")

        elif choice == "3":
            sender = await aioconsole.ainput("Nadawca (adres): ")
            recipient = await aioconsole.ainput("Odbiorca (adres): ")
            try:
                amount = float(await aioconsole.ainput("Kwota: "))
                if amount <= 0:
                    print("[ERROR] Kwota musi być większa od 0")
                    continue
                    
                if sender not in wallets:
                    print("[ERROR] Brak klucza prywatnego nadawcy")
                    continue
                
                # Sprawdź balans przed transakcją
                if blockchain.balances.get(sender, 0) < amount:
                    print("[ERROR] Niewystarczające środki")
                    continue
                    
                priv = wallets[sender]
                signature = sign_transaction(priv, sender, recipient, amount)
                if signature:
                    tx = Transaction(sender, recipient, amount, signature)
                    blockchain.add_transaction(tx)
                    if await send_to_server({'type': 'transaction', 'data': tx.to_dict()}):
                        print("[SUKCES] Dodano transakcję i wysłano do serwera")
            except ValueError:
                print("[ERROR] Nieprawidłowa kwota")

        elif choice == "4":
            miner = await aioconsole.ainput("Adres górnika (adres): ")
                
            print("[INFO] Rozpoczynam wydobywanie bloku...")
            blockchain.mine_block(miner)
            if await send_to_server({'type': 'chain', 'data': [b.to_dict() for b in blockchain.chain]}):
                print("[SUKCES] Blok wydobyty i wysłany do serwera!")

        elif choice == "5":
            print("\n=== BLOCKCHAIN ===")
            for i, block in enumerate(blockchain.chain):
                print(f"\nBlok #{i}:")
                print(json.dumps(block.to_dict(), indent=2))

        elif choice == "6":
            print("[INFO] Kończenie pracy...")
            if websocket:
                await websocket.close()
            break

        else:
            print("[ERROR] Nieprawidłowy wybór")

if __name__ == "__main__":
    try:
        asyncio.run(menu())
    except KeyboardInterrupt:
        print("\n[INFO] Kończenie pracy...")
        if websocket:
            asyncio.run(websocket.close())
        sys.exit(0)
