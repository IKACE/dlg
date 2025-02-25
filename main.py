# -*- coding: utf-8 -*-
import argparse
import numpy as np
from pprint import pprint

from PIL import Image
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import grad
import torchvision
from torchvision import models, datasets, transforms
print(torch.__version__, torchvision.__version__)

from utils import label_to_onehot, cross_entropy_for_onehot

parser = argparse.ArgumentParser(description='Deep Leakage from Gradients.')
parser.add_argument('--index', type=int, default="25",
                    help='the index for leaking images on CIFAR.')
parser.add_argument('--image', type=str,default="",
                    help='the path to customized image.')
parser.add_argument('--batch_size', type=int, default=2,
                    help="batch size")
args = parser.parse_args()

device = "cpu"
if torch.cuda.is_available():
    device = "cuda"
print("Running on %s" % device)

dst = datasets.CIFAR100("~/.torch", download=True)
tp = transforms.ToTensor()
tt = transforms.ToPILImage()

img_index = args.index
gt_data = tp(dst[img_index][0])

if len(args.image) > 1:
    gt_data = Image.open(args.image)
    gt_data = tp(gt_data)


gt_data = gt_data.view(1, *gt_data.size())
gt_label = torch.Tensor([dst[img_index][1]]).long()
gt_label = gt_label.view(1, )
gt_onehot_label = label_to_onehot(gt_label)

batched_gt_data = gt_data
batched_gt_label = gt_label
batched_gt_onehot = gt_onehot_label

for i in range(args.batch_size - 1):
    gt_data = tp(dst[100 + i][0]).view(*gt_data.size())
    gt_label = torch.Tensor([dst[100 + i][1]]).long().view(1, )
    gt_onehot_label = label_to_onehot(gt_label)
    batched_gt_data = torch.cat((batched_gt_data, gt_data), 0)
    batched_gt_onehot = torch.cat((batched_gt_onehot, gt_onehot_label), 0)

plt.imshow(tt(gt_data[0].cpu()))

batched_gt_data = batched_gt_data.to(device)
batched_gt_onehot = batched_gt_onehot.to(device)

from models.vision import LeNet, weights_init
net = LeNet().to(device)


torch.manual_seed(1234)

net.apply(weights_init)
criterion = cross_entropy_for_onehot

# compute original gradient 
pred = net(batched_gt_data)
y = criterion(pred, batched_gt_onehot)
dy_dx = torch.autograd.grad(y, net.parameters())

original_dy_dx = list((_.detach().clone() for _ in dy_dx))

# generate dummy data and label
dummy_data = torch.randn(batched_gt_data.size()).to(device).requires_grad_(True)
dummy_label = torch.randn(batched_gt_onehot.size()).to(device).requires_grad_(True)

# plt.imshow(tt(dummy_data[0].cpu()))

optimizer = torch.optim.LBFGS([dummy_data, dummy_label])


history = []
for iters in range(1000):
    def closure():
        optimizer.zero_grad()

        dummy_pred = net(dummy_data) 
        dummy_onehot_label = F.softmax(dummy_label, dim=-1)
        dummy_loss = criterion(dummy_pred, dummy_onehot_label) 
        dummy_dy_dx = torch.autograd.grad(dummy_loss, net.parameters(), create_graph=True)
        
        grad_diff = 0
        for gx, gy in zip(dummy_dy_dx, original_dy_dx): 
            grad_diff += ((gx - gy) ** 2).sum()
        grad_diff.backward()
        
        return grad_diff
    
    optimizer.step(closure)
    if iters % 10 == 0: 
        current_loss = closure()
        print(iters, "%.4f" % current_loss.item())
        history.append(tt(dummy_data[0].cpu()))

plt.figure(figsize=(12, 8))
for i in range(100):
    plt.subplot(10, 10, i + 1)
    plt.imshow(history[i])
    plt.title("iter=%d" % (i * 10))
    plt.axis('off')

plt.show()
