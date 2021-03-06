import math

import torch
import torch.nn as nn
from torch.nn.modules.utils import _pair
import sys
# sys.path.insert(0, "/rscratch/zhendong/yaohuic/CenterNet/src/lib/models/external/")
import os
dirname = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(dirname,"../"))
from functions.dcn_deform_conv import deform_conv, modulated_deform_conv


class DeformConv(nn.Module):

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=3,
                 stride=1,
                 padding=1,
                 dilation=1,
                 groups=1,
                 deformable_groups=1,
                 bias=False):
        super(DeformConv, self).__init__()

        assert not bias
        assert in_channels % groups == 0, \
            'in_channels {} cannot be divisible by groups {}'.format(
                in_channels, groups)
        assert out_channels % groups == 0, \
            'out_channels {} cannot be divisible by groups {}'.format(
                out_channels, groups)

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = _pair(kernel_size)
        self.stride = _pair(stride)
        self.padding = _pair(padding)
        self.dilation = _pair(dilation)
        self.groups = groups
        self.deformable_groups = deformable_groups

        self.weight = nn.Parameter(
            torch.Tensor(out_channels, in_channels // self.groups,
                         *self.kernel_size))

        self.reset_parameters()

    def reset_parameters(self):
        n = self.in_channels
        for k in self.kernel_size:
            n *= k
        stdv = 1. / math.sqrt(n)
        self.weight.data.uniform_(-stdv, stdv)

    def forward(self, x, offset):
        return deform_conv(x, offset, self.weight, self.stride, self.padding,
                           self.dilation, self.groups, self.deformable_groups)


class DeformConvPack(DeformConv):

    def __init__(self, *args, **kwargs):
        super(DeformConvPack, self).__init__(*args, **kwargs)

        self.conv_offset = nn.Conv2d(
            self.in_channels,
            self.deformable_groups * 2 * self.kernel_size[0] *
            self.kernel_size[1],
            kernel_size=self.kernel_size,
            stride=_pair(self.stride),
            padding=_pair(self.padding),
            bias=True)
        self.init_offset()

    def init_offset(self):
        self.conv_offset.weight.data.zero_()
        self.conv_offset.bias.data.zero_()

    def forward(self, x):
        offset = self.conv_offset(x)
        return deform_conv(x, offset, self.weight, self.stride, self.padding,
                           self.dilation, self.groups, self.deformable_groups)


class DeformConvPack1x1(DeformConv):

    def __init__(self, *args, **kwargs):
        super(DeformConvPack1x1, self).__init__(*args, **kwargs)

        self.conv_offset = nn.Conv2d(
            self.in_channels,
            self.deformable_groups * 2 * self.kernel_size[0] *
            self.kernel_size[1],
            kernel_size=1,
            stride=1,
            padding=0,
            bias=True)
        self.init_offset()

    def init_offset(self):
        self.conv_offset.weight.data.zero_()
        self.conv_offset.bias.data.zero_()

    def forward(self, x):
        offset = self.conv_offset(x)
        return deform_conv(x, offset, self.weight, self.stride, self.padding,
                           self.dilation, self.groups, self.deformable_groups)


class DeformConvPackDW(DeformConv):

    def __init__(self, *args, **kwargs):
        super(DeformConvPackDW, self).__init__(*args, **kwargs)

        # self.conv_offset = nn.Conv2d(
        #     self.in_channels,
        #     self.deformable_groups * 2 * self.kernel_size[0] *
        #     self.kernel_size[1],
        #     kernel_size=self.kernel_size,
        #     stride=_pair(self.stride),
        #     padding=_pair(self.padding),
        #     bias=True)
        inp = int(self.in_channels)
        oup = int(self.deformable_groups * 18)
        self.conv_dw = nn.Conv2d(inp, inp, 
                                 3, 1, 1, 
                                 groups=inp, 
                                 bias=True)
        self.conv_pw = nn.Conv2d(inp, oup, 1, 1, 0, bias=True)
        self.conv_pw.weight.data.zero_()
        self.conv_pw.bias.data.zero_()

    def forward(self, x):
        # offset = self.conv_offset(x)
        offset = self.conv_pw(self.conv_dw(x))
        return deform_conv(x, offset, self.weight, self.stride, self.padding,
                           self.dilation, self.groups, self.deformable_groups)


class ModulatedDeformConv(nn.Module):

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 stride=1,
                 padding=0,
                 dilation=1,
                 groups=1,
                 deformable_groups=1,
                 bias=False):
        super(ModulatedDeformConv, self).__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = _pair(kernel_size)
        self.stride = stride
        self.padding = padding
        self.dilation = dilation
        self.groups = groups
        self.deformable_groups = deformable_groups
        self.with_bias = bias

        self.weight = nn.Parameter(
            torch.Tensor(out_channels, in_channels // groups,
                         *self.kernel_size))
        if bias:
            self.bias = nn.Parameter(torch.Tensor(out_channels))
        else:
            self.register_parameter('bias', None)
        self.reset_parameters()

    def reset_parameters(self):
        n = self.in_channels
        for k in self.kernel_size:
            n *= k
        stdv = 1. / math.sqrt(n)
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.zero_()

    def forward(self, x, offset, mask):
        return modulated_deform_conv(x, offset, mask, self.weight, self.bias,
                                     self.stride, self.padding, self.dilation,
                                     self.groups, self.deformable_groups)


class ModulatedDeformConvPack(ModulatedDeformConv):

    def __init__(self, *args, **kwargs):
        super(ModulatedDeformConvPack, self).__init__(*args, **kwargs)

        self.conv_offset_mask = nn.Conv2d(
            self.in_channels,
            self.deformable_groups * 3 * self.kernel_size[0] *
            self.kernel_size[1],
            kernel_size=self.kernel_size,
            stride=_pair(self.stride),
            padding=_pair(self.padding),
            bias=True)
        self.init_offset()

    def init_offset(self):
        self.conv_offset_mask.weight.data.zero_()
        self.conv_offset_mask.bias.data.zero_()

    def forward(self, x):
        # print(x.shape)
        out = self.conv_offset_mask(x)
        o1, o2, mask = torch.chunk(out, 3, dim=1)
        offset = torch.cat((o1, o2), dim=1)
        mask = torch.sigmoid(mask)
        return modulated_deform_conv(x, offset, mask, self.weight, self.bias,
                                     self.stride, self.padding, self.dilation,
                                     self.groups, self.deformable_groups)


# class DeformConv(nn.Module):

#     def __init__(self, in_channels, out_channels, kernel_size=3, stride=1,
#                  padding=0, dilation=1, groups=1, deformable_groups=1, bias=True):
#         super(DeformConv, self).__init__()
#         assert in_channels % groups == 0, 'in_channels must be divisible by groups'
#         assert out_channels % groups == 0, 'out_channels must be divisible by groups'
#         assert out_channels % deformable_groups == 0, 'out_channels must be divisible by deformable groups'

#         self.in_channels = in_channels
#         self.out_channels = out_channels
#         self.kernel_size = _pair(kernel_size)
#         self.stride = _pair(stride)
#         self.padding = _pair(padding)
#         self.dilation = _pair(dilation)
#         self.groups = groups
#         self.deformable_groups = deformable_groups

#         self.weight = Parameter(torch.Tensor(
#             self.out_channels, self.in_channels // self.groups, *self.kernel_size).cuda())
#         if bias:
#             self.bias = Parameter(torch.Tensor(self.out_channels).cuda())
#         else:
#             self.register_parameter('bias', None)

#         self.reset_parameters()

#     def reset_parameters(self):
#         n = self.in_channels
#         for k in self.kernel_size:
#             n *= k
#         stdv = 1. / math.sqrt(n)
#         self.weight.data.uniform_(-stdv, stdv)
#         if self.bias is not None:
#             self.bias.data.uniform_(-stdv, stdv)

#     def forward(self, data, offset):
#         return DeformConvFunction.apply(data, offset, self.weight, self.bias, self.in_channels, self.out_channels,
#                                         self.kernel_size, self.stride, self.padding, self.dilation, self.groups,
#                                         self.deformable_groups)


# class DeformConvWithOffset(nn.Module):

#     def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False):
#         super(DeformConvWithOffset, self).__init__()
#         self.conv_offset = nn.Conv2d(in_channels, kernel_size * kernel_size *
#                                      2 * deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
#         self.conv_offset.weight.data.zero_()
#         self.conv_offset.bias.data.zero_()
#         self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
#                                padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

#     def forward(self, x):
#         return self.conv(x, self.conv_offset(x))


class DeformConvWithOffsetBound(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False, offset_bound=8):
        super(DeformConvWithOffsetBound, self).__init__()
        self.conv_offset = nn.Conv2d(in_channels, kernel_size * kernel_size *
                                     2 * deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_offset.weight.data.zero_()
        self.conv_offset.bias.data.zero_()
        self.conv_bound = torch.nn.Hardtanh(
            min_val=-offset_bound, max_val=offset_bound, inplace=True)
        self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

    def forward(self, x):
        return self.conv(x, self.conv_bound(self.conv_offset(x)))


class DeformConvWithOffsetRound(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False):
        super(DeformConvWithOffsetRound, self).__init__()
        self.conv_offset = nn.Conv2d(in_channels, kernel_size * kernel_size *
                                     2 * deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_offset.weight.data.zero_()
        self.conv_offset.bias.data.zero_()
        self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

    def forward(self, x):
        return self.conv(x, self.conv_offset(x).round_())


class DeformConvWithOffsetScale(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False):
        super(DeformConvWithOffsetScale, self).__init__()
        self.conv_scale = nn.Conv2d(
            in_channels, deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_scale.weight.data.zero_()
        # self.conv_scale.bias.data.zero_()
        nn.init.constant_(self.conv_scale.bias.data, 1)
        self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

        self.anchor_offset = torch.FloatTensor([-1, -1, -1, 0, -1, 1,
                                                0, -1,  0, 0,  0, 1,
                                                1, -1,  1, 0,  1, 1]).unsqueeze(0).unsqueeze(2).unsqueeze(2)

    def forward(self, x):
        o = self.anchor_offset.to(x.device) * (self.conv_scale(x) - 1)
        return self.conv(x, o)


class DeformConvWithOffsetScaleBound(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False, offset_bound=8):
        super(DeformConvWithOffsetScaleBound, self).__init__()
        self.conv_scale = nn.Conv2d(
            in_channels, deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_scale.weight.data.zero_()
        # self.conv_scale.bias.data.zero_()
        nn.init.constant_(self.conv_scale.bias.data, 1)
        self.conv_bound = torch.nn.Hardtanh(
            min_val=-offset_bound, max_val=offset_bound, inplace=True)
        self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

        self.anchor_offset = torch.FloatTensor([-1, -1, -1, 0, -1, 1,
                                                0, -1,  0, 0,  0, 1,
                                                1, -1,  1, 0,  1, 1]).unsqueeze(0).unsqueeze(2).unsqueeze(2)

    def forward(self, x):
        s = self.conv_bound(self.conv_scale(x))
        o = self.anchor_offset.to(x.device) * (s - 1)
        return self.conv(x, o)


class DeformConvWithOffsetScaleBoundPositive(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1,
                 groups=1, deformable_groups=1, bias=False, offset_bound=8, hidden_state=64, BN_MOMENTUM=0.1):
        super(DeformConvWithOffsetScaleBoundPositive, self).__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        # self.conv_scale = nn.Conv2d(in_channels, deformable_groups, kernel_size=1, stride=1, padding=0, bias=False)
        self.conv_scale = nn.Conv2d(in_channels, deformable_groups, kernel_size=1, stride=stride, padding=0, bias=True)
        # self.conv_scale = nn.Conv2d(in_channels, deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        # self.conv_scale = nn.Sequential(
        #     # pw
        #     nn.Conv2d(in_channels, hidden_state, 1, 1, 0, bias=False),
        #     nn.BatchNorm2d(hidden_state, momentum=BN_MOMENTUM),
        #     nn.ReLU(inplace=True),
        #     # dw
        #     nn.Conv2d(hidden_state, hidden_state, 3, 1, 1, groups=hidden_state, bias=False),
        #     nn.BatchNorm2d(hidden_state, momentum=BN_MOMENTUM),
        #     # pw-linear
        #     # nn.Conv2d(hidden_state, deformable_groups, 1, 1, 0, bias=False)
        #     nn.Conv2d(hidden_state, deformable_groups, 1, 1, 0, bias=True)
        # )

        for m in self.conv_scale.modules():
            if isinstance(m, nn.Conv2d):
                m.weight.data.zero_()
                if m.bias is not None:
                    print("initialize offset bias")
                    nn.init.constant_(m.bias, 1)
                    # nn.init.constant_(m.bias, 2)

        # if type(self.conv_scale) == nn.Conv2d:
        #     self.conv_scale.weight.data.zero_()
        #     if self.conv_scale.bias is not None:
        #         nn.init.constant_(self.conv_scale.bias.data, 1)

        # self.conv_scale.weight.data.zero_()
        # nn.init.constant_(self.conv_scale.bias.data, 1)

        self.conv_bound = torch.nn.Hardtanh(
            min_val=-offset_bound+1, max_val=offset_bound, inplace=True)
        # self.conv_bound = torch.nn.Hardtanh(
        #     min_val=-1, max_val=offset_bound-1, inplace=True)
        # self.conv_bound = torch.nn.Hardtanh(
        #     min_val=0, max_val=offset_bound, inplace=True)

        self.conv = DeformConv(in_channels, in_channels, kernel_size=kernel_size, stride=stride,
                       padding=padding, dilation=dilation, groups=in_channels, deformable_groups=deformable_groups,
                       bias=bias)

        # if in_channels != out_channels:
        if True:
            self.conv_channel = nn.Conv2d(in_channels, out_channels, 1, 1, 0, bias=False)

            if type(self.conv_channel) == nn.Conv2d:
                # nn.init.normal_(self.conv_channel.weight, std=0.001)
                torch.nn.init.kaiming_normal_(self.conv_channel.weight, nonlinearity='relu')
                # torch.nn.init.xavier_normal_(m.weight.data)
                if self.conv_channel.bias is not None:
                    nn.init.constant_(self.conv_channel.bias, 0)

        # self.conv = DeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
        #                        padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups,
        #                        bias=bias)

        self.anchor_offset = torch.FloatTensor([-1, -1, -1, 0, -1, 1,
                                                0, -1,  0, 0,  0, 1,
                                                1, -1,  1, 0,  1, 1]).unsqueeze(0).unsqueeze(2).unsqueeze(2)

    def forward(self, x):
        s = self.conv_bound(self.conv_scale(x))
        # o = self.anchor_offset.to(x.device) * s
        o = self.anchor_offset.to(x.device) * (s - 1)
        # o = self.anchor_offset.to(x.device) * (s - 2)
        # if self.in_channels != self.out_channels:
        if True:
            return self.conv_channel(self.conv(x, o))
        else:
            return self.conv(x, o)


class ModulatedDeformConvWithOffsetScaleBoundPositive(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False, offset_bound=8):
        super(ModulatedDeformConvWithOffsetScaleBoundPositive, self).__init__()
        self.conv_mask = nn.Conv2d(
            in_channels, deformable_groups * 9, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_scale = nn.Conv2d(
            in_channels, deformable_groups, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv_scale.weight.data.zero_()
        # self.conv_scale.bias.data.zero_()
        nn.init.constant_(self.conv_scale.bias.data, 1)
        self.conv_bound = torch.nn.Hardtanh(
            min_val=0, max_val=offset_bound, inplace=True)
        self.conv = ModulatedDeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

        self.anchor_offset = torch.FloatTensor([-1, -1, -1, 0, -1, 1,
                                                0, -1,  0, 0,  0, 1,
                                                1, -1,  1, 0,  1, 1]).unsqueeze(0).unsqueeze(2).unsqueeze(2)

    def forward(self, x):
        m = self.conv_mask(x)
        s = self.conv_bound(self.conv_scale(x))
        o = self.anchor_offset.to(x.device) * (s - 1)
        return self.conv(x, o, m)


class ModulatedDeformConvWithOffset1x1ScaleBoundPositive(nn.Module):

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, deformable_groups=1, bias=False, offset_bound=8):
        super(ModulatedDeformConvWithOffset1x1ScaleBoundPositive, self).__init__()
        self.conv_mask = nn.Conv2d(
            in_channels, deformable_groups * 9, kernel_size=1, stride=1, padding=0, bias=True)
        self.conv_scale = nn.Conv2d(
            in_channels, deformable_groups, kernel_size=1, stride=1, padding=0, bias=True)
        self.conv_scale.weight.data.zero_()
        # self.conv_scale.bias.data.zero_()
        nn.init.constant_(self.conv_scale.bias.data, 1)
        self.conv_bound = torch.nn.Hardtanh(
            min_val=0, max_val=offset_bound, inplace=True)
        self.conv = ModulatedDeformConv(in_channels, out_channels, kernel_size=kernel_size, stride=stride,
                               padding=padding, dilation=dilation, groups=groups, deformable_groups=deformable_groups, bias=bias)

        self.anchor_offset = torch.FloatTensor([-1, -1, -1, 0, -1, 1,
                                                0, -1,  0, 0,  0, 1,
                                                1, -1,  1, 0,  1, 1]).unsqueeze(0).unsqueeze(2).unsqueeze(2)

    def forward(self, x):
        m = self.conv_mask(x)
        s = self.conv_bound(self.conv_scale(x))
        o = self.anchor_offset.to(x.device) * (s - 1)
        return self.conv(x, o, m)
