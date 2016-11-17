# Squall #

The Squall is a framework which implements the cooperative multitasking
based on event-driven switching async/await coroutines.


#### This is contains several components (modules) ####

 * **squall.abc** -- Abstract base classes and interfaces.
 * **_squall** -- Low-level event dispatcher and I/O autobuffer designed
   for use with a callback functions.
 * **squall.coroutine** -- Implementation of event-driven coroutine switching.
 * **squall.network** -- Implementation of the network primitives used
   coroutines for async I/O.
