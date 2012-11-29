#!/usr/bin/env python

from cement.core import controller, foundation, backend, handler
import boto
import sys
import string

defaults = backend.defaults('base')
defaults['base']['AWS_REGIONS'] = ['us-east-1', 'us-west-2', 'us-west-1', 'eu-west-1', 
                                   'ap-southeast-1', 'ap-northeast-1', 'sa-east-1']

class BaseController(controller.CementBaseController):
    class Meta:
        label = 'base'
        description = 'AWS CLI.'
        configuration_defaults = defaults
        arguments = [
                  (['-r', '--region'], dict(
                        default=defaults['base']['AWS_REGIONS'][0], 
                        choices=defaults['base']['AWS_REGIONS'], 
                        nargs=1, 
                        help="Set AWS regional context."))
                  ]
    
    @controller.expose(hide=True, aliases=['run', 'help'])
    def default(self):
        print self._usage_text
        print self._help_text
        
class StackController(controller.CementBaseController):
    class Meta:
        label = 'stack'
        description = 'Control teh stackz'
        arguments = [
             (['-t', '--template-file'], dict(help="Path to the template file")),
             (['-s','--stack-name'], dict(help="Name of the stack")),
             (['-p','--parameters'], dict(nargs='+', help="Parameters to pass to stack")),
             (['-a','--all'], dict(action='store_true', help="Disable all filters")),
             (['-b','--batch-mode'], dict(action='store_true', help="Enable batch mode")),
             (['--disable-rollback'], dict(default=False, action='store_true', 
                                           help='Disable rollback if stack creation fails')
              ),
             (['--timeout'], dict(default=30, type=int, help='Set the timeout on stack creation')),
             (['-u', '--update'], dict(default=False, action='store_true', help='Update an existing stack'))
             ]
        
    @controller.expose(aliases=['help'])
    def default(self):
        print self._usage_text
        print self._help_text
    
    @controller.expose(help="Lists stacks.")
    def list(self):
        conn = boto.connect_cloudformation()
        
        stack_status_filters=["CREATE_IN_PROGRESS", "CREATE_FAILED", "CREATE_COMPLETE",
            "DELETE_IN_PROGRESS", "DELETE_FAILED", "ROLLBACK_COMPLETE", "UPDATE_COMPLETE"] if self.pargs.all == False else []
        stacks = conn.list_stacks(stack_status_filters=stack_status_filters)
        output_data = {}
        for stack in stacks:
            print '%s\t%s' % (stack.stack_name, stack.stack_status)
            
    @controller.expose(help="Launch stacks.")
    def launch(self):
        ## Ensure that both the template file and stack name are provided
        if self.pargs.template_file == None or self.pargs.stack_name == None:
            self.log.error('Please provide missing --template-file and/or --stack-name')
            sys.exit(1)
        
        ## Ensure that the template file can be read
        try:
            template_file_fp = open(self.pargs.template_file)
        except IOError:
            self.log.error('Could not open --template-file bro.')
            sys.exit(1)
        
        ## Open a connection to the API
        conn = boto.connect_cloudformation()
        
        ## Attempt to validate the template. Blow up if its invalid
        try:
            template_body = template_file_fp.read()
            template = conn.validate_template(template_body)
        except Exception as e:
            self.log.error(e)
            sys.exit(1)
            
        capabilities = []
            
        try:
            capabilities.append(template.member)
        except AttributeError:
            pass
            
        ## Dictionary that holds the template parameters and values
        p_params = dict()
        
        ## The API kindly returns the template parameters with default values, if successful.
        ## Stick em in our dictionary. No homo
        for template_parameter in template.template_parameters:
            p_params[template_parameter.parameter_key] = template_parameter.default_value
            
        ## If --parameters was provided, parse it and auto-fill the template parameters values
        if self.pargs.parameters:
            for param in self.pargs.parameters:
                param_parts = param.split('=')
                if len(param_parts) == 2:
                    if p_params.has_key(param_parts[0]):
                        p_params[param_parts[0]] = param_parts[1]
                        
        for param in p_params:
            if p_params[param] == None:
                if self.pargs.batch_mode == True:
                    self.log.error('Missing parameter and no default given: "%s"' % param)
                    sys.exit(1)
                else:
                    new_value = raw_input('[Parameter] %s: ' % param)
                    p_params[param] = new_value
                    
        print 'Stack Name\t\t: %s' % self.pargs.stack_name
        print 'Template\t\t: %s' % template_file_fp.name
        
        params = []
        if len(p_params) > 0:
            print 'Stack Parameters'
            for param in p_params:
                params.append((param, p_params[param]))
                print '\t%s : %s' % (param, p_params[param])
            
        print 'Capabilites\t\t: %s' % ('None' if len(capabilities)==0 else '|'.join(capabilities))
        print 'Disable Rollback\t\t: %s' % self.pargs.disable_rollback
        print 'Timeout\t\t: %s' % self.pargs.timeout
        
        is_ok = raw_input('Is this OK? [y/n]')
        if is_ok!='y':
            return
        
        try:
            if self.pargs.update == False:
                stack_id = conn.create_stack(stack_name=self.pargs.stack_name, template_body=template_body, 
                                  parameters=params, disable_rollback=self.pargs.disable_rollback, 
                                  timeout_in_minutes=self.pargs.timeout, capabilities=capabilities)
                print 'Stack created: %s[%s]' % (self.pargs.stack_name, stack_id)
            else:
                stack_id = conn.update_stack(stack_name=self.pargs.stack_name, template_body=template_body, 
                              parameters=params, disable_rollback=self.pargs.disable_rollback, 
                              timeout_in_minutes=self.pargs.timeout, capabilities=capabilities)
                print 'Stack updated: %s[%s]' % (self.pargs.stack_name, stack_id)
        except Exception as e:
            self.log.error(e.error_message)
            sys.exit(1)
            
    @controller.expose(help="Destroy stacks.")
    def destroy(self):
        if self.pargs.stack_name == None:
            print 'Please provide a stack name'
            sys.exit(1)
            
        is_ok = raw_input('About to destroy %s\nIs this OK? [y/n]:' % self.pargs.stack_name)
        if is_ok!='y':
            return
        try:
            conn = boto.connect_cloudformation()
            result = conn.delete_stack(self.pargs.stack_name)
            print result
        except Exception as e:
            self.log.error(e)
            sys.exit(1)
        
    @controller.expose(help="Describe stack.")
    def describe(self):
        if self.pargs.stack_name == None:
            print 'Please provide a stack name'
            sys.exit(1)
            
        try:
            conn = boto.connect_cloudformation()
            stacks = conn.describe_stacks(self.pargs.stack_name)
            stack = None
            if len(stacks) == 0:
                raise Exception("No stacks found matching '%s'" % self.pargs.stack_name)
            else:
                stack = stacks[0]
                
            stack_events = conn.describe_stack_events(self.pargs.stack_name)
            
            print '%s [%s]:' % (self.pargs.stack_name, stack.stack_status)
            print 'Creation Time\t: %s' % stack.creation_time
            print 'Description\t: %s' % stack.description
            if len(stack.outputs) > 0:
                print 'Outputs\t:'
                for output in stack.outputs:
                    print '\t%s: %s' % (output.key, output.value)
                    
            if len(stack_events) > 0:
                print 'Events\t:'
                for stack_event in stack_events:
                    print '[%s]\t\t\t\t\t[%s] \n\t%s %s \n\t%s \n\tReason: %s \n_________________________________________________________________________________'% (
                      stack_event.timestamp, stack_event.resource_status, 
                      stack_event.resource_type, stack_event.logical_resource_id, 
                      stack_event.physical_resource_id, 
                      stack_event.resource_status_reason)
        except Exception as e:
            self.log.error(e)
            sys.exit(1)
            
#TODO: Use scheduled group actions to control the scaling instead of just settings the desired capacity
class ScaleController(controller.CementBaseController):
    class Meta:
        label = 'scale'
        description = 'Control teh scalingz'
        arguments = [
                     (['-g', '--group'], dict(action='append', help="")),
                     (['-l', '--limit'], dict( help="")),
                     (['-c', '--capacity'], dict( help=""))
                     ]
    
    @controller.expose(aliases=['help'])
    def default(self):
        print self._usage_text
        print self._help_text
            
    @controller.expose(aliases=['ls'])
    def list(self):
        ec2as = boto.connect_autoscale()
        grps = ec2as.get_all_groups(max_records=self.pargs.limit)
        for grp in grps:
            print '%s [min=%s max=%s capacity=%s] AZs[%s]' % (grp.name, grp.min_size, grp.max_size, grp.desired_capacity, 'None' if grp.availability_zones == None else string.join(grp.availability_zones, ', '))
       
    @controller.expose()
    def showlog(self):
        if self.pargs.group == None:
            selg.log.error('Please provide at least one group name with --group')
            return
        else:
            ec2as = boto.connect_autoscale()
            grps = ec2as.get_all_groups(self.pargs.group)
            for grp in grps:
                logs = grp.get_activities(max_records=self.pargs.limit)
                for log in logs:
                    print '[%s-%s][%s] %s >> %s' % (log.start_time, log.end_time, log.status_message, log.description, log.cause)
        
    @controller.expose()
    def capacity(self):
        if self.pargs.capacity == None or self.pargs.group == None:
            self.log.error('Please provide a capacity and/or group to set with --capacity and --group')
            return
        else:
            ec2as = boto.connect_autoscale()
            grps = ec2as.get_all_groups(self.pargs.group)
            for grp in grps:
                status = grp.set_capacity(self.pargs.capacity)
                print 'Status Response: %s' % status
                
class AWSCli(foundation.CementApp):
    class Meta:
        label = 'aws-cli'
        base_controller = BaseController
    
app = AWSCli()
handler.register(StackController)
handler.register(ScaleController)

try:
    app.setup()
    app.run()
finally:
    app.close()
    
