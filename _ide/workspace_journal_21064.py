# 2026-04-16T20:20:11.262827600
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

comp = client.get_component(name="lwip_echo_server")
status = comp.clean()

status = platform.build()

comp.build()

vitis.dispose()

vitis.dispose()

