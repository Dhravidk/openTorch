import torch
import torch.nn as nn

class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer = nn.Conv2d(3, 8, kernel_size=3)

    def forward(self, x):
        return self.layer(x)


def build_model():
    return Model()
