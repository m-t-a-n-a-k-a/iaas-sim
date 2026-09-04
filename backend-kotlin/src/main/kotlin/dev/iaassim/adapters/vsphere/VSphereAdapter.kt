package dev.iaassim.adapters.vsphere

import com.vmware.sdk.vsphere.utils.PropertyCollectorHelper
import com.vmware.sdk.vsphere.utils.VcenterClientFactory
import com.vmware.vim25.ManagedObjectReference
import com.vmware.vim25.ManagedObjectNotFoundFaultMsg
import com.vmware.vim25.ManagedObjectType
import com.vmware.vim25.OptionValue
import com.vmware.vim25.VirtualMachinePowerState
import dev.iaassim.application.BackendVirtualMachineRef
import dev.iaassim.application.ObservedVirtualMachine
import dev.iaassim.application.VirtualMachineBackendError
import dev.iaassim.application.VirtualMachineBackendFailure
import dev.iaassim.application.VirtualMachineBackendNotFound
import dev.iaassim.application.VirtualMachinePort
import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import java.util.UUID

private const val CREATION_MARKER = "iaas-sim.internal.publicVirtualMachineId"

data class VSphereConfiguration(
    val host: String = System.getenv("VSPHERE_HOST") ?: "127.0.0.1",
    val port: Int = (System.getenv("VSPHERE_PORT") ?: "8989").toInt(),
    val username: String = System.getenv("VSPHERE_USERNAME") ?: "user",
    val password: String = System.getenv("VSPHERE_PASSWORD") ?: "pass",
)

class VSphereAdapter(private val configuration: VSphereConfiguration = VSphereConfiguration()) : VirtualMachinePort {
    override fun listVirtualMachines(): Outcome<List<ObservedVirtualMachine>, VirtualMachineBackendFailure> =
        try {
            connect().use { client ->
                val helper = PropertyCollectorHelper(client.vimPort, client.vimServiceContent)
                val references = helper.getObjects(
                    client.vimServiceContent.rootFolder,
                    ManagedObjectType.VIRTUAL_MACHINE,
                ).values.flatten()
                val properties = helper.fetchProperties(
                    references,
                    "name", "summary.runtime.powerState", "config.extraConfig",
                )
                Ok(references.map { reference -> project(reference, properties[reference]) })
            }
        } catch (exception: Exception) {
            Err(VirtualMachineBackendFailure("list", safeReason(exception)))
        }

    override fun getVirtualMachine(
        backendRef: BackendVirtualMachineRef,
    ): Outcome<ObservedVirtualMachine, VirtualMachineBackendError> = try {
        connect().use { client ->
            val helper = PropertyCollectorHelper(client.vimPort, client.vimServiceContent)
            val reference = ManagedObjectReference().apply {
                type = "VirtualMachine"
                value = backendRef.value
            }
            val properties = helper.fetchProperties(reference, "name", "summary.runtime.powerState", "config.extraConfig")
            if (properties.isEmpty() || properties["name"] == null) {
                Err(VirtualMachineBackendNotFound(backendRef))
            } else {
                Ok(project(reference, properties))
            }
        }
    } catch (_: ManagedObjectNotFoundFaultMsg) {
        Err(VirtualMachineBackendNotFound(backendRef))
    } catch (exception: Exception) {
        Err(VirtualMachineBackendFailure("get", safeReason(exception)))
    }

    private fun connect() = VcenterClientFactory(
        configuration.host,
        configuration.port,
        30_000,
        60_000,
        true,
        null,
    ).createClient(configuration.username, configuration.password, null)

    private fun project(
        reference: ManagedObjectReference,
        nullableProperties: Map<String, *>?,
    ): ObservedVirtualMachine {
        val properties = nullableProperties ?: error("VM properties unavailable")
        val name = when (val rawName = properties["name"]) {
            is String -> rawName
            else -> error("VM name unavailable")
        }
        val powerState = when (properties["summary.runtime.powerState"]) {
            VirtualMachinePowerState.POWERED_ON -> PowerState.RUNNING
            VirtualMachinePowerState.POWERED_OFF -> PowerState.STOPPED
            else -> error("unsupported VM power state")
        }
        return ObservedVirtualMachine(
            BackendVirtualMachineRef(reference.value),
            name,
            powerState,
            when (val extraConfig = properties["config.extraConfig"]) {
                null -> null
                is List<*> -> creationMarker(extraConfig)
                else -> error("malformed VM extraConfig")
            },
        )
    }

    private fun creationMarker(options: List<*>): VirtualMachineId? {
        val values = options.filterIsInstance<OptionValue>().filter { it.key == CREATION_MARKER }.map { it.value }
        if (values.isEmpty()) return null
        val marker = when (val value = values.singleOrNull()) {
            is String -> value
            else -> error("malformed duplicate creation marker")
        }
        val parsed = UUID.fromString(marker)
        if (parsed.version() != 7) error("creation marker is not UUIDv7")
        return VirtualMachineId(parsed)
    }

    private fun safeReason(exception: Exception): String = exception::class.simpleName ?: "SDK failure"
}
