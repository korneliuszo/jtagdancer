#!/usr/bin/env python3

import jtagdancer
import time

dancer=jtagdancer.JTAGDancer(open("STM32F405_415_407_417_LQFP100.json"),"cmsis-dap","stm32f4x_bs.cfg")
print("AAA", dancer.pins["PB13"].get_input())
#print(dancer.bs_in)
#print(dancer.bs_out)

dancer.pins["PE7"].set_en(True)
dancer.pins["PE7"].set_output(True)
dancer.update()
#print(dancer.bs_in)
#print(dancer.bs_out)
print("AAA", dancer.pins["PB13"].get_input())

import timeit
print("1000 updates took:", timeit.timeit(dancer.update, number=1000))
