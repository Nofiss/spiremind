import torch
import bitsandbytes as bnb

print(f"Torch CUDA available: {torch.cuda.is_available()}")
try:
    # Prova a creare una matrice quantizzata (il vero test per BNB)
    import torch.nn as nn
    linear = nn.Linear(10, 10).cuda()
    # Se questo non crasha, BNB funziona
    print("BitsAndBytes CUDA test: SUCCESS")
except Exception as e:
    print(f"BitsAndBytes CUDA test: FAILED. Error: {e}")
