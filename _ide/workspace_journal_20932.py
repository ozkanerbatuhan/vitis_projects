# 2026-04-21T18:01:33.018986900
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

status = comp.clean()

status = platform.build()

status = platform.build()

comp.build()

vitis.dispose()

vitis.dispose()

