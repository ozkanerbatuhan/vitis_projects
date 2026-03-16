# 2026-03-16T19:29:14.881403100
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.build()

comp = client.get_component(name="mlp_app")
comp.build()

domain = platform.get_domain(name="zynq_fsbl")

status = domain.set_lib(lib_name="lwip220", path="D:\AMDDesignTools\2025.2\Vitis\data\embeddedsw\ThirdParty\sw_services\lwip220_v1_3")

status = domain.regenerate()

status = domain.set_config(option = "lib", param = "lwip220_dhcp", value = "true", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "lwip220_lwip_dhcp_does_acd_check", value = "true", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "lwip220_pbuf_pool_size", value = "2048", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "XILTIMER_en_interval_timer", value = "true", lib_name="xiltimer")

status = platform.build()

status = platform.build()

status = domain.regenerate()

status = platform.build()

domain = platform.get_domain(name="standalone_ps7_cortexa9_0")

status = domain.set_config(option = "lib", param = "lwip220_dhcp", value = "true", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "lwip220_lwip_dhcp_does_acd_check", value = "true", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "lwip220_pbuf_pool_size", value = "2048", lib_name="lwip220")

status = domain.set_config(option = "lib", param = "XILTIMER_en_interval_timer", value = "true", lib_name="xiltimer")

status = platform.build()

comp = client.create_app_component(name="lwip_echo_server",platform = "$COMPONENT_LOCATION/../mlp_platform/export/mlp_platform/mlp_platform.xpfm",domain = "standalone_ps7_cortexa9_0",template = "lwip_echo_server")

status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = platform.update_hw(hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa")

status = platform.build()

status = comp.clean()

status = platform.build()

comp.build()

vitis.dispose()

