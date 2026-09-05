package dev.iaassim.adapters.vsphere

import com.vmware.sdk.vsphere.utils.PropertyCollectorHelper
import com.vmware.sdk.vsphere.utils.VcenterClientFactory
import com.vmware.vim25.ArrayOfOptionValue
import com.vmware.vim25.ManagedObjectReference
import com.vmware.vim25.ManagedObjectNotFoundFaultMsg
import com.vmware.vim25.ManagedObjectType
import com.vmware.vim25.OptionValue
import com.vmware.vim25.VirtualMachineConfigSpec
import com.vmware.vim25.VirtualMachineFileInfo
import com.vmware.vim25.VirtualMachinePowerState
import com.vmware.vim25.TaskInfoState
import dev.iaassim.application.BackendOperationFailed
import dev.iaassim.application.BackendOperationPort
import dev.iaassim.application.BackendOperationRef
import dev.iaassim.application.BackendOperationRunning
import dev.iaassim.application.BackendOperationStatus
import dev.iaassim.application.BackendOperationSucceeded
import dev.iaassim.application.OperationPollingFailure
import dev.iaassim.application.PowerCommandBackendSubmissionFailure
import dev.iaassim.application.BackendVirtualMachineRef
import dev.iaassim.application.ObservedVirtualMachine
import dev.iaassim.application.VirtualMachineBackendError
import dev.iaassim.application.VirtualMachineBackendFailure
import dev.iaassim.application.VirtualMachineBackendNotFound
import dev.iaassim.application.VirtualMachinePort
import dev.iaassim.application.VirtualMachineCreateSpec
import dev.iaassim.application.VirtualMachineCreateBackendSubmissionFailure
import dev.iaassim.application.BackendVirtualMachineCreated
import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import java.security.KeyStore
import java.util.UUID

private const val CREATION_MARKER = "iaas-sim.internal.publicVirtualMachineId"

data class VSphereConfiguration(
    val host: String = System.getenv("VSPHERE_HOST") ?: "127.0.0.1",
    val port: Int = (System.getenv("VSPHERE_PORT") ?: "8989").toInt(),
    val username: String = System.getenv("VSPHERE_USERNAME") ?: "user",
    val password: String = System.getenv("VSPHERE_PASSWORD") ?: "pass",
)

class VSphereAdapter(private val configuration: VSphereConfiguration = VSphereConfiguration()) :
    VirtualMachinePort, BackendOperationPort {
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
                Ok(properties.entries.map { (reference, vmProperties) -> project(reference, vmProperties) })
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

    override fun submitPowerCommand(backendRef: BackendVirtualMachineRef, command: PowerCommand):
        Outcome<BackendOperationRef, PowerCommandBackendSubmissionFailure> = try {
        connect().use { client ->
            val vm = ManagedObjectReference().apply { type = "VirtualMachine"; value = backendRef.value }
            val task = when (command) {
                PowerCommand.START -> client.vimPort.powerOnVMTask(vm, null)
                PowerCommand.STOP -> client.vimPort.powerOffVMTask(vm)
            }
            Ok(BackendOperationRef(task.value))
        }
    } catch (exception: Exception) {
        Err(PowerCommandBackendSubmissionFailure(backendRef, safeReason(exception)))
    }

    override fun submitCreateVirtualMachine(virtualMachineId: VirtualMachineId, spec: VirtualMachineCreateSpec):
        Outcome<BackendOperationRef, VirtualMachineCreateBackendSubmissionFailure> = try {
        connect().use { client ->
            val helper = PropertyCollectorHelper(client.vimPort, client.vimServiceContent)
            val datacenter = firstByName(helper, client.vimServiceContent.rootFolder, ManagedObjectType.DATACENTER)
            val pool = firstByName(helper, client.vimServiceContent.rootFolder, ManagedObjectType.RESOURCE_POOL).first
            val datastore = firstByName(helper, datacenter.first, ManagedObjectType.DATASTORE)
            val folderValue = helper.fetchProperties(datacenter.first, "vmFolder")["vmFolder"]
            val folder = when (folderValue) { is ManagedObjectReference -> folderValue; else -> error("Datacenter VM folder unavailable") }
            val config = VirtualMachineConfigSpec().apply {
                name = spec.name
                numCPUs = spec.vcpus
                memoryMB = spec.memoryMiB.toLong()
                guestId = "otherGuest64"
                files = VirtualMachineFileInfo().apply { vmPathName = "[${datastore.second}]" }
                extraConfig.add(OptionValue().apply { key = CREATION_MARKER; value = virtualMachineId.value.toString() })
            }
            Ok(BackendOperationRef(client.vimPort.createVMTask(folder, config, pool, null).value))
        }
    } catch (exception: Exception) { Err(VirtualMachineCreateBackendSubmissionFailure(safeReason(exception))) }

    override fun getOperationStatus(backendRef: BackendOperationRef):
        Outcome<BackendOperationStatus, OperationPollingFailure> = try {
        connect().use { client ->
            val task = ManagedObjectReference().apply { type = "Task"; value = backendRef.value }
            val properties = PropertyCollectorHelper(client.vimPort, client.vimServiceContent)
                .fetchProperties(task, "info.state", "info.error", "info.result")
            when (properties["info.state"]) {
                TaskInfoState.QUEUED, TaskInfoState.RUNNING -> Ok(BackendOperationRunning)
                TaskInfoState.SUCCESS -> when (val value = properties["info.result"]) {
                    null -> Ok(BackendOperationSucceeded())
                    is ManagedObjectReference -> if (value.type == "VirtualMachine")
                        Ok(BackendOperationSucceeded(BackendVirtualMachineCreated(BackendVirtualMachineRef(value.value))))
                    else Err(OperationPollingFailure("unsupported backend task result"))
                    else -> Err(OperationPollingFailure("unsupported backend task result"))
                }
                TaskInfoState.ERROR -> Ok(BackendOperationFailed("backend task reported error"))
                else -> Err(OperationPollingFailure("unsupported backend task state"))
            }
        }
    } catch (exception: Exception) { Err(OperationPollingFailure(safeReason(exception))) }

    private fun connect() = VcenterClientFactory(
        configuration.host,
        configuration.port,
        30_000,
        60_000,
        false,
        emptyTrustStore(),
    ).createClient(configuration.username, configuration.password, null)

    private fun firstByName(helper: PropertyCollectorHelper, root: ManagedObjectReference,
        type: ManagedObjectType): Pair<ManagedObjectReference, String> {
        val references = helper.getObjects(root, type).values.flatten()
        val named = helper.fetchProperties(references, "name").entries.map { (reference, properties) ->
            val name = when (val value = properties?.get("name")) { is String -> value; else -> error("inventory name unavailable") }
            Pair(reference, name)
        }
        return named.sortedWith(compareBy<Pair<ManagedObjectReference, String>> { it.second }.thenBy { it.first.value }).first()
    }

    private fun emptyTrustStore(): KeyStore = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
        load(null, null)
    }

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
                is ArrayOfOptionValue -> creationMarker(extraConfig.optionValue)
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

    private fun safeReason(exception: Exception): String = generateSequence<Throwable>(exception) { it.cause }
        .take(3)
        .joinToString(" <- ") { cause ->
            val className = cause::class.qualifiedName ?: cause.javaClass.name
            cause.message?.let { "$className: $it" } ?: className
        }
}
