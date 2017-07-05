import argparse
import numpy as np
from load_data import *
import torch
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

import models.cnn as model

from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import confusion_matrix, accuracy_score

parser = argparse.ArgumentParser(description='PyTorch Basic 2-Layer Language ID Classifier')
parser.add_argument('--lr', type=float, default=1e-3,
                    help='initial learning rate')
parser.add_argument('--epochs', type=int, default=5,
                    help='upper epoch limit')
parser.add_argument('--batch-size', type=int, default=8, metavar='b',
                    help='batch size')
parser.add_argument('--languages', type=str, nargs='+', default=None,
                    help='languages to filter by')
parser.add_argument('--seed', type=int, default=1111,
                    help='random seed')
parser.add_argument('--cuda', action='store_true',
                    help='use CUDA')
parser.add_argument('--validate', action='store_true',
                    help='do out-of-bag validation')
parser.add_argument('--use-chromagrams', action='store_true',
                    help='use chromagrams')
parser.add_argument('--log-interval', type=int, default=4, metavar='N',
                    help='reports per epoch')
parser.add_argument('--file-list', type=str, default="data/trainingset.csv",
                    help='csv file with audio files and labels')
parser.add_argument('--load-grams', action='store_true',
                    help='load spectro/chroma -grams')
parser.add_argument('--load-model', action='store_true',
                    help='load model from disk')
parser.add_argument('--save-model', action='store_true',
                    help='path to save the final model')
args = parser.parse_args()

# set seed
torch.manual_seed(args.seed)

# load spectro/chroma -grams
inputs, labels = get_grams(use_chromagrams = args.use_chromagrams,
                           load_grams_from_disk = args.load_grams,
                           languages = args.languages, use_log10 = True)
le = LabelEncoder()
le.fit(labels)
labels_encoded = le.transform(labels)
num_targets = le.classes_.shape[0]


# Create Network
gtype = "chroma" if args.use_chromagrams else "spectra"
model_save_path = "output/states/cnn_model_"+gtype+".pt"
net = model.Net(num_targets)
if args.load_model:
    net.load_state_dict(torch.load(model_save_path))
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(net.parameters(), lr=args.lr)
print(net)

# create training and testing sets
b = args.batch_size
shuffle_inputs = True
if args.validate:
    train_frac = 0.8
else:
    train_frac = 1.0
train_idx = int(len(inputs) * train_frac)
inputs_training = inputs[:train_idx]
labels_training = labels_encoded[:train_idx]
inputs_training = torch.from_numpy(inputs_training).float()
inputs_training.unsqueeze_(1)
labels_training = torch.from_numpy(labels_training)
trainset = TensorDataset(inputs_training, labels_training)
trainloader = DataLoader(trainset, batch_size=b, shuffle=shuffle_inputs)

if args.validate:
    inputs_testing = inputs[train_idx:]
    inputs_testing = torch.from_numpy(inputs_testing).float()
    inputs_testing.unsqueeze_(1)
    labels_testing = labels_encoded[train_idx:]

# calculate number of minibatches
# per epoch variables
epochs = args.epochs
minibatches = train_idx // b
print_freq = minibatches // args.log_interval
print("Epochs:", epochs)
print("Minibatches Per Epoch:", minibatches)
print("Print Frequency (minibatches):", print_freq)
net.train() # set model into training mode
for epoch in range(epochs):  # loop over the dataset multiple times
    # reset vars each epoch
    running_loss = 0.0
    for i, (minibatch, l) in enumerate(trainloader):
        i += 1
        n = i*b if i*b < inputs_training.size()[0] else inputs_training.size()[0]
        # get minibatch
        minibatch, l = Variable(minibatch), Variable(l)
        # zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize
        outputs = net(minibatch)
        loss = criterion(outputs, l)
        loss.backward()
        optimizer.step()

        # print statistics
        running_loss += loss.data[0]

        if i % print_freq == (print_freq-1):
            print('[%d, %5d, %d] loss: %.5f' %
                  (epoch + 1, i + 1, (i*b), running_loss / n)) # average loss in epoch
    if args.validate:
        net.eval() # set model into evaluation mode
        outputs = net(Variable(inputs_testing))
        outputs_labels = outputs.max(1)[1].data.numpy().ravel()
        print("Validation Accuracy: %.2f"%accuracy_score(labels_testing, outputs_labels))
        net.train() # reset to training mode
print('Finished Training')

# Prediction
net.eval() # set model into evaluation mode
outputs = net(Variable(inputs_testing))
outputs_labels = outputs.max(1)[1].data.numpy().ravel()
print(outputs_labels.shape)

yhat = le.inverse_transform(outputs_labels)
y_t = le.inverse_transform(labels_testing)
print(sorted([x for x in zip(yhat,y_t)]))
print(accuracy_score(y_t, yhat))
print(confusion_matrix(y_t, yhat))
if args.save_model:
    torch.save(net.state_dict(), model_save_path)