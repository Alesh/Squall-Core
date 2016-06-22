Squall
======

The Squall is the nano-framework that implements cooperative event-driven
concurrency and asynchronous networking.

The goal of version 0.1 is achieved
===================================
The goal of version 0.1 is achieved. It is a good idea, and it should be
continued. The next goal - a more convenient and faster interface that must
be production ready.


Goal of version 0.2
===================

 * Split a SocketStream it into two parts: SocketAutoBuffer based on
   callbacks; and IOStream that implements just asynchronous I/O. Then
   rewrite SocketAutoBuffer as Python C extension module.

 * Join SAGIGateway and SCGIBackend to one class SCGIGateway and
   do it more easy.

 * Develop the adapter from SCGIGateway to WSGI application.

 * Tests and documentation completely cover source.
