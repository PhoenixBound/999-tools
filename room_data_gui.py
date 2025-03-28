import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import sys
import json
import threading

# Verifica se o módulo room_data está disponível
try:
    import room_data
except ModuleNotFoundError:
    messagebox.showerror(
        "Erro de Importação",
        "O módulo 'room_data.py' não foi encontrado.\n"
        "Certifique-se de que o arquivo 'room_data.py' está no mesmo diretório que este script."
    )
    sys.exit(1)  # Encerra o programa se o módulo não for encontrado

class RoomDataGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("999 Room.dat Tool")
        self.root.resizable(False, False)
        
        # Configuração do estilo
        self.style = ttk.Style()
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TButton', font=('Arial', 10), padding=5)
        self.style.configure('TCheckbutton', background='#f0f0f0')
        self.style.map('TButton', background=[('active', '#d9d9d9')])
        
        # Variáveis
        self.room_dat_path = tk.StringVar()
        self.json_path = tk.StringVar()
        self.ptbr_var = tk.BooleanVar(value=False)
        
        # Criação dos widgets
        self.create_widgets()
        
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack()

        # Seção Room.dat
        ttk.Label(main_frame, text="Arquivo room.dat:", font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=2)
        room_frame = ttk.Frame(main_frame)
        room_frame.grid(row=1, column=0, sticky='ew', pady=5)
        ttk.Entry(room_frame, textvariable=self.room_dat_path, width=40).pack(side='left', padx=(0, 5))
        ttk.Button(room_frame, text="Procurar", command=self.browse_room_dat).pack(side='left')

        # Seção JSON
        ttk.Label(main_frame, text="Arquivo JSON:", font=('Arial', 10)).grid(row=2, column=0, sticky='w', pady=2)
        json_frame = ttk.Frame(main_frame)
        json_frame.grid(row=3, column=0, sticky='ew', pady=5)
        ttk.Entry(json_frame, textvariable=self.json_path, width=40).pack(side='left', padx=(0, 5))
        ttk.Button(json_frame, text="Procurar", command=self.browse_json).pack(side='left')

        # Opção PT-BR
        ttk.Checkbutton(main_frame, text="Usar codificação Latin-1 (PT-BR)", variable=self.ptbr_var).grid(row=4, column=0, sticky='w', pady=10)

        # Botões de ação
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, pady=10)
        ttk.Button(btn_frame, text="Extrair JSON", command=self.extract_json).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Inserir JSON", command=self.insert_json).pack(side='left', padx=5)

        # Barra de progresso
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", length=300, mode="indeterminate")
        self.progress.grid(row=6, column=0, pady=(10, 0))

        # Status
        self.status_label = ttk.Label(main_frame, text="Pronto.", foreground='#666666', font=('Arial', 9))
        self.status_label.grid(row=7, column=0, sticky='w', pady=(10, 0))

    def browse_room_dat(self):
        path = filedialog.askopenfilename(filetypes=[("DAT files", "*.dat")])
        if path:
            self.room_dat_path.set(path)

    def browse_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if path:
            self.json_path.set(path)

    def extract_json(self):
        if not self.validate_paths(require_json=False):
            return
        
        # Inicia a barra de progresso
        self.progress.start()
        self.update_status("Extraindo JSON...")
        
        # Executa em uma thread separada para não travar a interface
        threading.Thread(target=self._extract_json_thread, daemon=True).start()

    def _extract_json_thread(self):
        try:
            with open(self.room_dat_path.get(), 'rb') as f:
                room_dat = f.read()
            
            display_encoding = 'latin_1' if self.ptbr_var.get() else None
            structured = room_data.dump(room_dat, display_encoding)
            
            with open(self.json_path.get(), 'w', encoding='utf-8', newline='\n') as f:
                json.dump(structured, f, ensure_ascii=False, indent=4)
            
            self.update_status("Extração concluída com sucesso!", success=True)
        except Exception as e:
            self.update_status(f"Erro na extração: {str(e)}", success=False)
            messagebox.showerror("Erro", str(e))
        finally:
            self.progress.stop()

    def insert_json(self):
        if not self.validate_paths(require_json=True):
            return
        
        # Inicia a barra de progresso
        self.progress.start()
        self.update_status("Inserindo JSON...")
        
        # Executa em uma thread separada para não travar a interface
        threading.Thread(target=self._insert_json_thread, daemon=True).start()

    def _insert_json_thread(self):
        try:
            # Define a codificação com base na opção PT-BR
            encoding = 'latin_1' if self.ptbr_var.get() else 'utf-8'
            
            # Abre o arquivo JSON com a codificação correta
            with open(self.json_path.get(), 'r', encoding=encoding) as f:
                structured = json.load(f)
            
            display_encoding = 'latin_1' if self.ptbr_var.get() else None
            output = room_data.make_sir0_from_obj_list(structured, display_encoding)
            
            with open(self.room_dat_path.get(), 'wb') as f:
                f.write(output)
            
            self.update_status("Inserção concluída com sucesso!", success=True)
        except Exception as e:
            self.update_status(f"Erro na inserção: {str(e)}", success=False)
            messagebox.showerror("Erro", str(e))
        finally:
            self.progress.stop()

    def validate_paths(self, require_json=True):
        if not os.path.exists(self.room_dat_path.get()):
            messagebox.showerror("Erro", "Arquivo room.dat não encontrado!")
            return False
        if require_json and not os.path.exists(self.json_path.get()):
            messagebox.showerror("Erro", "Arquivo JSON não encontrado!")
            return False
        return True

    def update_status(self, message, success=True):
        color = '#4CAF50' if success else '#F44336'
        self.status_label.config(text=message, foreground=color)

if __name__ == "__main__":
    root = tk.Tk()
    app = RoomDataGUI(root)
    root.mainloop()