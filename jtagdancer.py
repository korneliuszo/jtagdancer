#!/usr/bin/env python3

import json
import bitarray
import bitarray.util
import subprocess
import time
import socket
import copy

def hexify(d):
	ba=bitarray.bitarray("".join([x.replace("X","0") for x in d]))
	ba.reverse()
	ba.fill()
	ba.reverse()
	hexes=[bitarray.util.ba2hex(ba[x:x+32]) for x in range(0,len(ba),32)]
	return " ".join(hexes)

class PIN():
	def get_input(self):
		raise Exception("not valid")
	def get_output(self):
		raise Exception("not valid")
	def set_output(self,val):
		raise Exception("not valid")
	def get_en(self):
		raise Exception("not valid")
	def set_en(self,val):
		raise Exception("not valid")

class JTAGDancer():
	def __init__(self, jsonfile,adapter,scan_file):
		bsdl=json.load(jsonfile)
		frequency=int(float([ x["tap_scan_clock"]["frequency"] for x in bsdl["scan_port_identification"] if "tap_scan_clock" in x.keys()][0])/1000)
		openocd_args = ["openocd", "-clog_output /dev/null",  f"-finterface/{adapter}.cfg", "-ctransport select jtag", f"-cadapter speed {frequency}", f"-f{scan_file}"]

		self.idcode = dict([(x["instruction_name"],hexify(x["opcode_list"][0])) for x in bsdl["instruction_register_description"]["instruction_opcodes"]])

		self.bs_len = int(bsdl["boundary_scan_register_description"]["fixed_boundary_stmts"]["boundary_length"])

		pins=set([x["cell_info"]["cell_spec"]["port_id"] for x in bsdl["boundary_scan_register_description"]["fixed_boundary_stmts"]["boundary_register"]])

		pins.remove("*")

		self.pins=dict([(pin,PIN()) for pin in pins])

		self.bs_in=bitarray.bitarray(self.bs_len)
		self.bs_in.fill()
		self.bs_out=bitarray.bitarray(self.bs_len)
		self.bs_out.fill()

		for cell in  bsdl["boundary_scan_register_description"]["fixed_boundary_stmts"]["boundary_register"]:
			safe=cell["cell_info"]["cell_spec"]["safe_bit"]
			bit_no = int(cell["cell_number"])
			self.bs_out[bit_no] = safe != "0"

			if cell["cell_info"]["cell_spec"]["function"] == "INPUT":
				self.pins[cell["cell_info"]["cell_spec"]["port_id"]].get_input = lambda bit_no=bit_no: self.get_bitin(bit_no)
			if cell["cell_info"]["cell_spec"]["function"] == "OUTPUT3":
				self.pins[cell["cell_info"]["cell_spec"]["port_id"]].get_output = lambda bit_no=bit_no: self.get_bitout(bit_no)
				self.pins[cell["cell_info"]["cell_spec"]["port_id"]].set_output = lambda val, bit_no=bit_no: self.set_bitout(bit_no,val)
				cell_en_no = cell["cell_info"]["input_or_disable_spec"]["control_cell"]
				cell_en_polarity = cell["cell_info"]["input_or_disable_spec"]["disable_value"] == "1"
				#cell_en = [c for c in bsdl["boundary_scan_register_description"]["fixed_boundary_stmts"]["boundary_register"] if c["cell_number"] == cell_en_no][0]
				self.pins[cell["cell_info"]["cell_spec"]["port_id"]].get_en = lambda bit_no=int(cell_en_no),cell_en_polarity=cell_en_polarity: self.get_biten(bit_no,cell_en_polarity)
				self.pins[cell["cell_info"]["cell_spec"]["port_id"]].set_en = lambda val, bit_no=int(cell_en_no),cell_en_polarity=cell_en_polarity: self.set_biten(bit_no,cell_en_polarity,val)

		self.openocd = subprocess.Popen(openocd_args)
		time.sleep(1)

		self.conn=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		self.conn.connect(("127.0.0.1",6666))

		self.set_idcode("PRELOAD")
		self.update()
		self.set_idcode("EXTEST")

	def __del__(self):
		self.ocd_command("shutdown")
		self.openocd.wait()
		pass

	def get_bitin(self,bit):
		return bool(self.bs_in[bit])
	def get_bitout(self,bit):
		return bool(self.bs_out[bit])
	def set_bitout(self,bit,val):
		self.bs_out[bit] = val
	def get_biten(self,bit,en):
		return bool(self.bs_out[bit])^en
	def set_biten(self,bit,en,val):
		self.bs_out[bit] = val^en

	def ocd_command(self, cmd):
		#print(">",cmd)
		self.conn.send(cmd.encode('ascii')+b'\x1a')
		buff = b''
		while b'\x1a' not in buff:
			c=self.conn.recv(1024)
			buff+=c
		line,sep,buff = buff.partition(b'\x1a')
		recv=line.decode('ascii')
		#print("<",recv)
		return recv

	def set_idcode(self,code):
		self.ocd_command(f"irscan jtagdancer.bs {self.idcode[code]}")

	def update(self):
		a=copy.copy(self.bs_out)
		a.reverse()
		hexes=bitarray.util.ba2hex(a)
		f_len=(len(hexes)-len(hexes)//8*8)
		blen=self.bs_len-self.bs_len//32*32
		hex_split=([f"{blen if x == f_len else 32} 0x{hexes[x-(f_len if x==f_len else 8):x]}" for x in range(len(hexes),0,-8)])
		hex_in=self.ocd_command(f"drscan jtagdancer.bs {' '.join(hex_split)}")
		inp=hex_in.split(' ')
		inp.reverse()
		self.bs_in=bitarray.util.hex2ba("".join(inp))
		self.bs_in.reverse()

