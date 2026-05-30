# 2026-05-30T15:13:38.666753600
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = platform.build()

comp.build()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

status = platform.build()

comp.build()

status = platform.build()

comp.build()

status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = comp.clean()

status = platform.build()

comp.build()

status = platform.update_hw(hw_design = "D:\vivado projects\hft\mlp_system_wrapper.xsa")

status = platform.update_hw(hw_design = "D:\vivado projects\hft\mlp_system_wrapper.xsa")

status = platform.update_hw(hw_design = "D:\vivado projects\hft\mlp_system_wrapper.xsa")

status = platform.update_hw(hw_design = "D:\vivado projects\hft\mlp_system_wrapper.xsa")

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

status = platform.build()

comp.build()

status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

status = comp.clean()

status = platform.build()

comp.build()

vitis.dispose()

vitis.dispose()

