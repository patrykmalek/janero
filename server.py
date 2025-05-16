import json
import time
import asyncio
import websockets
import signal
import sys
from blockchain import Blockchain, Transaction, Block

blockchain = Blockchain()
running = True
connected_clients = set()

def initialize_blockchain():
    """Inicjalizuje blockchain z blokiem genesis"""
    if len(blockchain.chain) == 0:
        genesis_block = Block(
            index=0,
            timestamp=time.time(),
            transactions=[],
            previous_hash="0" * 64,
            nonce=0
        )
        genesis_block.hash = genesis_block.compute_hash()
        blockchain.chain.append(genesis_block)
        print("[INFO] Utworzono blok genesis")
        update_balances()

def update_balances():
    """Aktualizuje balanse na podstawie łańcucha bloków"""
    blockchain.balances.clear()
    
    for block in blockchain.chain:
        for tx in block.transactions:
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

async def handle_client(websocket):
    print("[INFO] Nowe połączenie WebSocket")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            try:
                print("[INFO] Otrzymano wiadomość od klienta")
                payload = json.loads(message)
                response = None

                if payload['type'] == 'sync':
                    response = {'type': 'chain', 'data': [b.to_dict() for b in blockchain.chain]}
                    await websocket.send(json.dumps(response))
                    continue

                elif payload['type'] == 'chain':
                    new_chain = [Block.from_dict(b) for b in payload['data']]
                    blockchain.replace_chain(new_chain)
                    update_balances()
                    print("[INFO] Zaktualizowano łańcuch")
                    response = {'type': 'chain', 'data': [b.to_dict() for b in blockchain.chain]}

                elif payload['type'] == 'transaction':
                    tx = Transaction.from_dict(payload['data'])
                    blockchain.add_transaction(tx)
                    print("[INFO] Dodano transakcję")
                    response = {'type': 'pending_transactions', 'data': [tx.to_dict() for tx in blockchain.pending_transactions]}
                    print(blockchain.pending_transactions, tx)

                if response:
                    print("[INFO] Wysyłanie odpowiedzi do klientów")
                    websockets_to_remove = set()
                    for client in connected_clients:
                        try:
                            await client.send(json.dumps(response))
                            print("[INFO] Wysłano odpowiedź do klienta")
                        except websockets.exceptions.ConnectionClosed:
                            print("[INFO] Klient rozłączył się podczas wysyłania")
                            websockets_to_remove.add(client)
                        except Exception as e:
                            print(f"[ERROR] Błąd wysyłania do klienta: {e}")
                            websockets_to_remove.add(client)
                    
                    connected_clients.difference_update(websockets_to_remove)
                    print(f"[INFO] Aktywni klienci: {len(connected_clients)}")

            except json.JSONDecodeError:
                print("[ERROR] Nieprawidłowy format JSON")
                continue
            except Exception as e:
                print(f"[ERROR] Błąd przetwarzania danych: {e}")
                continue

    except websockets.exceptions.ConnectionClosed:
        print("[INFO] Klient rozłączył się")
    except Exception as e:
        print(f"[ERROR] Błąd obsługi klienta: {e}")
    finally:
        connected_clients.remove(websocket)
        print(f"[INFO] Usunięto klienta. Pozostało klientów: {len(connected_clients)}")

async def start_server():
    initialize_blockchain()
    
    server = await websockets.serve(
        handle_client,
        '0.0.0.0',
        5000,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=None
    )
    print("[INFO] Serwer WebSocket nasłuchuje na porcie 5000...")
    print("[INFO] Dostępny pod adresem: ws://0.0.0.0:5000")
    
    await server.wait_closed()

def signal_handler(signum, frame):
    global running
    print("\n[INFO] Otrzymano sygnał zakończenia, zamykanie serwera...")
    running = False
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    asyncio.run(start_server())
